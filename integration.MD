# Backend Integration Guide (Frontend)
This file is the practical API contract for integrating the current backend implementation with frontend flows.
## 1) Base URL and auth model
- Base URL: `http://localhost:8000/api/v1` (adjust for deployed env)
- Auth: Bearer JWT (`Authorization: Bearer <accessToken>`)
- Login model:
  1. `POST /auth/nonce`
  2. Wallet signs nonce message
  3. `POST /auth/verify` -> returns `accessToken`
- Logout: `POST /auth/logout` (marks session revoked in DB)
## 2) Endpoint inventory (implemented)
## Auth
- `POST /auth/nonce`
- `POST /auth/verify`
- `GET /auth/me`
- `POST /auth/logout`
## Maps
- `GET /maps/autocomplete?q=...&country=...`
- `GET /maps/place/{place_id}`
- `POST /routes/estimate`
## Pricing
- `POST /pricing/estimate`
## Marketplace
- `POST /rides`
- `GET /rides/{ride_id}`
- `GET /driver-feed/open-rides`
- `POST /rides/{ride_id}/offers`
- `GET /rides/{ride_id}/offers`
- `POST /rides/{ride_id}/select-driver`
## Tx prep and tx lifecycle
- `POST /tx/accept-ride`
- `POST /tx/record`
- `GET /tx/{tx_hash}`
## Treasury
- `POST /rides/{ride_id}/complete/sign`
## Chain sync
- `POST /webhooks/chain-events`
## Location stream (REST)
- `POST /rides/{ride_id}/locations`
- `GET /rides/{ride_id}/locations/latest`
## 3) Request/response payload contracts (core)
## `POST /auth/nonce`
Request:
{
  "wallet": "0x..."
}
Response:
{
  "nonce": "...",
  "expiresAt": "ISO8601"
}
## `POST /auth/verify`
Request:
{
  "wallet": "0x...",
  "nonce": "...",
  "signature": "0x..."
}
Response:
{
  "accessToken": "...",
  "tokenType": "Bearer"
}
## `POST /rides`
Request:
{
  "pickupLat": 12.9716,
  "pickupLng": 77.5946,
  "pickupAddress": "MG Road, Bengaluru",
  "dropLat": 12.9352,
  "dropLng": 77.6245,
  "dropAddress": "Koramangala, Bengaluru",
  "distanceMeters": 6200,
  "durationSeconds": 1320,
  "tipType": "percent",
  "tipValue": 8,
  "tipWei": "71736000000000"
}
Response:
- `RideResponse` (includes `id`, `status`, `selectedDriverWallet`, timestamps)
## `POST /rides/{ride_id}/offers`
Request:
{
  "etaSeconds": 420,
  "quotedFareWei": "900000000000000",
  "message": "Can reach fast"
}
Response:
- `OfferResponse`
## `POST /rides/{ride_id}/select-driver`
Request:
{
  "offerId": "uuid"
}
Response:
- Updated `RideResponse` with `status=DRIVER_SELECTED`
## `POST /pricing/estimate`
Request:
{
  "distanceMeters": 6200,
  "durationSeconds": 1320,
  "tipType": "percent",
  "tipValue": 8,
  "ceilingEnabled": true
}
Response:
{
  "baseFareWei": 854000000000000,
  "distanceComponentWei": 434000000000000,
  "timeComponentWei": 220000000000000,
  "surgeMultiplier": 1.0,
  "serviceFeeWei": 42700000000000,
  "tipWei": 71736000000000,
  "estimatedTotalWei": 968436000000000,
  "ceilingBondWei": 170800000000000,
  "requiredMsgValueWei": 1024800000000000
}
## `POST /tx/accept-ride`
Request:
{
  "rideId": "uuid",
  "driverSignature": "0x...",
  "ceilingEnabled": true,
  "chainId": 11155111,
  "driverNonce": 0
}
Response:
{
  "contractAddress": "0x...",
  "functionName": "acceptRide",
  "riderWallet": "0x...",
  "driverWallet": "0x...",
  "fareWei": "860000000000000",
  "ceilingEnabled": true,
  "ceilingBondWei": "172000000000000",
  "requiredMsgValueWei": "1032000000000000",
  "driverSignature": "0x...",
  "rideId": "uuid",
  "chainId": 11155111,
  "driverNonce": 0
}
## `POST /tx/record`
Request:
{
  "txHash": "0x...",
  "chainId": 11155111,
  "action": "acceptRide",
  "rideRequestId": "uuid",
  "status": "submitted"
}
Response:
- `TxRecordResponse`
## `GET /tx/{tx_hash}`
Response:
{
  "txHash": "0x...",
  "status": "submitted|pending|confirmed|failed",
  "chainId": 11155111,
  "action": "acceptRide",
  "rideRequestId": "uuid",
  "blockNumber": 1234567,
  "confirmedAt": "ISO8601|null"
}
## `POST /rides/{ride_id}/complete/sign`
Request:
{
  "onChainRideId": 7,
  "finalFareWei": "860000000000000",
  "chainId": 11155111
}
Response:
{
  "treasurySignature": "0x...",
  "onChainRideId": 7,
  "finalFareWei": "860000000000000",
  "riderWallet": "0x...",
  "driverWallet": "0x...",
  "chainId": 11155111
}
## `POST /webhooks/chain-events`
Request:
{
  "events": [
    {
      "eventName": "RideAccepted",
      "txHash": "0x...",
      "chainId": 11155111,
      "rideRequestId": "uuid",
      "blockNumber": 12345,
      "logIndex": 0,
      "fromWallet": "0x...",
      "driverWallet": "0x...",
      "status": "confirmed",
      "action": "acceptRide",
      "payload": {}
    }
  ]
}
Response:
{
  "processed": 1
}
## `POST /rides/{ride_id}/locations`
Request:
{
  "lat": 12.9401,
  "lng": 77.6202,
  "heading": 90.0,
  "speed": 10.2
}
Response:
- `LocationResponse`
## `GET /rides/{ride_id}/locations/latest`
Response:
- latest `LocationResponse`
## 4) Frontend orchestration sequence (recommended)
## Ride request to driver selection
1. Login (nonce + verify).
2. Maps autocomplete/place/route.
3. Pricing estimate.
4. Create ride.
5. Driver polls open rides and posts offers.
6. Rider fetches offers and selects driver.
## On-chain accept and tracking
7. Rider calls `/tx/accept-ride`.
8. Frontend wallet submits contract tx.
9. Frontend calls `/tx/record`.
10. Frontend polls `/tx/{hash}` until confirmed/failed.
11. Chain webhook updates ride status (provider -> backend).
## During trip and completion
12. Selected driver posts `/rides/{id}/locations`.
13. Rider reads `/rides/{id}/locations/latest` (polling).
14. Driver or rider calls `/rides/{id}/complete/sign`.
15. Frontend wallet submits `completeRide(...)` with treasury signature.
16. Frontend records completion tx and polls tx status.
17. Chain webhook marks ride completed.
## 5) Access control rules to follow in frontend
- `select-driver`: only ride owner.
- `locations` write: only selected driver.
- `locations/latest` read: only rider or selected driver.
- `complete/sign`: only rider or selected driver.
- `tx/accept-ride`: only ride owner.
## 6) Integration notes
- Backend currently provides tx prep for `acceptRide` only.
- Start/cancel/rate tx-prep endpoints can be added later similarly.
- WebSocket realtime endpoint is not yet implemented; use polling for now.
- All tests currently pass, including full E2E flow tests.
