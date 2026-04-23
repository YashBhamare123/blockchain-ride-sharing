# Ride Sharing dApp Backend Context (MVP)
This document is for AI agents and developers implementing the backend without repeatedly reverse-engineering the frontend.
## 1) Project intent
Build a ride-sharing app where:
- Ride lifecycle and core payments are enforced by the `Carpool` smart contract.
- Frontend (already present in `rideshare-hub/`) handles wallet connection, signing, and transaction submission.
- FastAPI backend handles everything off-chain: auth/session, maps/geocoding, distance+fare estimates, ride matching, treasury signatures, realtime updates, and chain-event syncing.
## 2) Existing frontend context (high-level)
- Frontend stack is React + TypeScript + Vite.
- Wallet/web3 packages include `ethers` and Reown AppKit.
- Maps package includes `@react-google-maps/api`.
- No reliable backend documentation currently exists; this file is the source of truth for MVP backend scope.
## 3) Smart contract context (Carpool)
Contract manages:
- Driver onboarding by owner (`registerDriver`) and collateral flow.
- User registration (`registerUser`).
- Ride acceptance/start/completion/cancel/dispute with escrow-like payment movement.
- Shared ride flow (`joinSharedRide`) with signatures from rider-1 and driver.
- Completion requires a treasury signature over:
  - `keccak256(abi.encodePacked("COMPLETE", id, finalFare, user, driver, chainid))`
- Rider rating of driver post-completion.

Important contract implications:
- `acceptRide` currently stores one selected driver in the on-chain ride.
- Product requirement allows multiple driver offers first, then rider chooses one.
- Therefore, multi-driver bidding must be modeled off-chain, and only the chosen driver is finalized on-chain via `acceptRide`.
## 4) Architecture split (authoritative)
## On-chain responsibilities
- Trust-minimized payment settlement.
- Immutable ride state transitions enforced by contract logic.
- Collateral and final payout/refund logic.
## FastAPI responsibilities
- Wallet-based auth/session management for app APIs.
- Google Maps integration (autocomplete/place/route estimation).
- Off-chain ride request board and driver offer collection.
- Selection flow (rider picks one driver).
- Compute and expose payable estimates including optional tip.
- Generate treasury completion signature.
- Realtime ride/location updates.
- Chain event ingestion and status synchronization.
## Backend architecture diagram (MVP)
```mermaid
flowchart LR
    subgraph C[Client Apps]
        R[Rider Frontend]
        D[Driver Frontend]
    end

    subgraph B[FastAPI Backend]
        A[Auth API\nnonce + verify + JWT]
        M[Maps Service\nPlaces + Routes]
        P[Pricing Service\nfare + tip + bond preview]
        RM[Ride Marketplace\nrequests + offers + select driver]
        TX[Tx Prep API\ncalldata + msg.value]
        TS[Treasury Signer\ncompleteRide signature]
        RT[Realtime Layer\nWebSocket + location stream]
        IDX[Chain Sync\nwebhook ingest + tx status]
        DB[(Postgres / Supabase)]
    end

    subgraph BC[Blockchain]
        CP[Carpool Contract]
    end

    subgraph GP[Google Platform]
        MAPS[Google Maps APIs]
    end

    R -->|SIWE login| A
    D -->|SIWE login| A
    A <--> DB

    R -->|pickup/drop search| M
    D -->|route/ETA support| M
    M <--> MAPS

    R -->|estimate fare + tip| P
    P --> M
    P <--> DB

    R -->|post ride| RM
    D -->|view open rides / place offer| RM
    RM <--> DB

    R -->|request tx payloads| TX
    D -->|request tx payloads| TX
    TX --> CP

    R -->|complete/sign request| TS
    D -->|complete/sign request| TS
    TS -->|treasury sig| R
    TS -->|treasury sig| D

    D -->|GPS pings| RT
    R -->|live ride updates| RT
    RT <--> DB

    CP -->|events| IDX
    IDX <--> DB
    R -->|tx status polling| IDX
    D -->|tx status polling| IDX
```
## 5) MVP data model (off-chain, minimal)
Suggested entities:
- `users`: wallet, role, created_at.
- `drivers`: wallet, availability, last_location, rating_cache.
- `ride_requests`: id (UUID), rider_wallet, pickup/drop coordinates + labels, status, selected_driver_wallet (nullable), tip fields.
- `driver_offers`: id, ride_request_id, driver_wallet, eta_seconds, quoted_fare_wei, optional_note, status.
- `ride_locations`: ride_request_id, driver_wallet, lat, lng, heading, speed, timestamp.
- `tx_records`: ride_request_id, action, tx_hash, chain_id, status.

Status enums (off-chain):
- Ride request: `OPEN`, `DRIVER_SELECTED`, `ONCHAIN_ACCEPTED`, `STARTED`, `COMPLETED`, `CANCELLED`, `DISPUTED`.
- Driver offer: `PENDING`, `WITHDRAWN`, `REJECTED`, `SELECTED`.
## 6) MVP endpoint list (with maps integration)
Base prefix: `/api/v1`
### A) Auth
1. `POST /auth/nonce`
- Purpose: issue SIWE-style nonce.
- Request: `{ "wallet": "0x..." }`
- Response: `{ "nonce": "...", "expiresAt": "..." }`

2. `POST /auth/verify`
- Purpose: verify signed nonce and return token.
- Request: `{ "wallet": "0x...", "signature": "0x...", "nonce": "..." }`
- Response: `{ "accessToken": "...", "tokenType": "Bearer" }`

3. `GET /me`
- Purpose: current app user/driver profile context.
- Auth required.
### B) Maps + pricing
4. `GET /maps/autocomplete?q=...`
- Purpose: Google Places autocomplete.
- Response: normalized place predictions.

5. `GET /maps/place/{place_id}`
- Purpose: place details (lat/lng, address components).

6. `POST /routes/estimate`
- Purpose: route distance, duration, polyline between pickup/drop.
- Request:
  - pickup `{lat,lng}`
  - drop `{lat,lng}`
- Response:
  - `distanceMeters`, `durationSeconds`, `polyline`

7. `POST /pricing/estimate`
- Purpose: appx fare preview with optional tip and ceiling-bond preview.
- Request:
  - `distanceMeters`, `durationSeconds`
  - `tipType`: `fixed|percent`
  - `tipValue`
  - optional `ceilingEnabled`
- Response:
  - `baseFareWei`, `surgeMultiplier`, `serviceFeeWei`, `tipWei`, `estimatedTotalWei`
  - if ceiling enabled: `ceilingBondWei`, `requiredMsgValueWei`
### C) Ride marketplace (off-chain matching before on-chain lock-in)
8. `POST /rides`
- Purpose: rider posts ride request visible to nearby drivers.
- Request:
  - pickup/drop data
  - optional `tipType`, `tipValue`, notes
- Response: created `rideRequestId`, initial status.

9. `GET /rides/{ride_id}`
- Purpose: canonical off-chain ride request state for UI.

10. `GET /driver-feed/open-rides`
- Purpose: driver sees nearby open requests.
- Query: optional geo filter, radius, pagination.

11. `POST /rides/{ride_id}/offers`
- Purpose: driver submits offer for rider consideration.
- Request:
  - `etaSeconds`
  - `quotedFareWei`
  - optional message

12. `GET /rides/{ride_id}/offers`
- Purpose: rider lists all offers.

13. `POST /rides/{ride_id}/select-driver`
- Purpose: rider picks one driver (required before on-chain `acceptRide`).
- Effect: mark one offer `SELECTED`, others `REJECTED`.
### D) Contract transaction preparation + signing support
Design principle:
- Backend does not send user wallet transactions.
- Backend returns call data and exact `msg.value` so frontend wallet can submit.

14. `POST /tx/accept-ride`
- Maps to contract `acceptRide(driver, fare, ceiling, sig)`.
- Input: chosen driver, fare, ceiling flag, driver signature.
- Output: contract address, function args, `requiredMsgValueWei`.

15. `POST /tx/start-ride`
- Maps to `startRide(id,a,b,c,d)`.

16. `POST /tx/cancel-ride`
- Maps to `cancelRide(id)`.

17. `POST /tx/rate-driver`
- Maps to `rateDriver(id,rating)`.

18. `POST /rides/{ride_id}/complete/sign`
- Purpose: treasury signs completion payload required by contract.
- Input: `onChainRideId`, `finalFareWei`, `user`, `driver`, `chainId`.
- Output: `treasurySignature`.

19. `POST /tx/complete-ride`
- Maps to `completeRide(id,finalFare,treasurySig)`.
- Output: prepared calldata.
### E) Realtime + location
20. `POST /rides/{ride_id}/locations`
- Purpose: driver GPS pings during active ride.

21. `GET /rides/{ride_id}/locations/latest`
- Purpose: rider polls latest known driver position.

22. `WS /ws/rides/{ride_id}`
- Purpose: push ride status changes, selected driver updates, and location events.
### F) Chain sync
23. `POST /webhooks/chain-events`
- Purpose: ingest provider webhook events (`RideAccepted`, `RideStarted`, `RideCompleted`, etc.) and update off-chain state.

24. `GET /tx/{tx_hash}`
- Purpose: tx status for frontend confirmation UX.
## 7) Core user flows (MVP)
## Flow A: Rider creates request and chooses driver
1. Rider logs in via wallet signature.
2. Rider uses maps autocomplete + route estimate + pricing estimate.
3. Rider posts `/rides`.
4. Drivers fetch `/driver-feed/open-rides` and post offers.
5. Rider reads `/rides/{id}/offers` and calls `/select-driver`.
6. Frontend obtains `/tx/accept-ride` payload and submits contract tx.

## Flow B: Start and complete ride
1. Selected driver starts trip via `/tx/start-ride` + wallet send.
2. Driver app sends periodic `/locations` updates.
3. At completion, backend treasury signs via `/complete/sign`.
4. Frontend submits `completeRide` using `/tx/complete-ride`.
5. Rider rates via `/tx/rate-driver`.

## Flow C: Cancellation/dispute (MVP minimal)
- Cancel: prepare and send `cancelRide`.
- Dispute can be deferred to post-MVP unless required immediately.
## 8) Security and operational notes
- Validate wallet ownership for every authenticated action.
- Store nonces with expiration and one-time use.
- Use strict authz:
  - only ride owner can select driver,
  - only assigned/selected driver can post active updates after lock-in.
- Rate-limit maps endpoints and location pings.
- Protect treasury key:
  - sign only server-side,
  - never expose private key to frontend/client.
- Verify chain ID in all signing/tx prep flows.
## 9) Suggested backend directory layout (FastAPI)
Example:
- `backend/app/main.py`
- `backend/app/api/v1/endpoints/auth.py`
- `backend/app/api/v1/endpoints/maps.py`
- `backend/app/api/v1/endpoints/rides.py`
- `backend/app/api/v1/endpoints/offers.py`
- `backend/app/api/v1/endpoints/tx.py`
- `backend/app/api/v1/endpoints/ws.py`
- `backend/app/api/v1/endpoints/webhooks.py`
- `backend/app/services/maps_service.py`
- `backend/app/services/pricing_service.py`
- `backend/app/services/chain_service.py`
- `backend/app/services/treasury_signer.py`
- `backend/app/models/*`
- `backend/app/schemas/*`
## 9.1) Local Postgres container configuration
Use a local Postgres container with:
- Container name: `offchain`
- Host: `localhost`
- Port: `5432` (standard Postgres port)
- User: `postgres`
- Password: `password`

Set the database name explicitly in env (example below uses `offchain` as DB name only if you create it):
- `DATABASE_URL=postgresql+psycopg2://postgres:password@localhost:5432/offchain`
## 10) Out-of-scope for MVP (defer)
- Full shared-ride UX for second rider (`joinSharedRide`) unless explicitly prioritized.
- Advanced surge ML model.
- Dynamic route re-pricing with penalties/refunds beyond current contract behavior.
- Multi-chain support.
## 11) Final implementation rule
For multi-driver acceptance product behavior:
- Keep multiple offers off-chain.
- Commit only chosen driver and chosen fare to on-chain `acceptRide`.
- Treat blockchain event as source of truth after tx confirmation.
