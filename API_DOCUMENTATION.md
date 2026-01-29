# API Documentation

## Enhanced Web Contractor API

This API has been enhanced with security, validation, rate limiting, and structured responses.

## Base URL
```
http://localhost:5000
```

## Security Features

### Rate Limiting
- **Default limits**: 200 requests/day, 50 requests/hour per IP
- **Endpoint-specific limits**:
  - `/api/stats`: 30 requests/minute
  - `/api/leads`: 60 requests/minute
  - `/api/process/start`: 10 requests/minute
  - `/api/process/stop`: 10 requests/minute
  - `/api/analytics`: 20 requests/minute
  - `/api/quality/check`: 5 requests/minute
  - `/api/review/action`: 10 requests/minute

### Input Validation
- All POST endpoints validate JSON payloads against schemas
- All GET endpoints validate query parameters
- Invalid requests return structured error responses

### Security Headers
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Referrer-Policy: strict-origin-when-cross-origin`

### CORS Configuration
- Only allows requests from `http://localhost:3000` and `http://127.0.0.1:3000`

## Response Format

### Success Response
```json
{
  "success": true,
  "data": { ... },
  "message": "Operation completed successfully",
  "timestamp": "2026-01-29T14:46:47.454602",
  "path": "/api/endpoint"
}
```

### Error Response
```json
{
  "error": true,
  "message": "Error description",
  "timestamp": "2026-01-29T14:46:47.454602",
  "path": "/api/endpoint",
  "validation_errors": { ... } // Only for validation errors
}
```

## Endpoints

### Statistics
```
GET /api/stats
```
Returns comprehensive pipeline statistics.

### Leads Management
```
GET /api/leads?page=1&per_page=20&status=&bucket=
```
Returns paginated leads with optional filtering.

### Process Management
```
POST /api/process/start
Content-Type: application/json

{
  "process": "stage0|stage_a|stage_b|stage_c|full_pipeline|quality_control|email_sender"
}
```

```
GET /api/process/status
```
Returns status of all running processes.

```
POST /api/process/stop
Content-Type: application/json

{
  "process": "process_name"
}
```

### Pipeline Management
```
GET /api/pipeline/status
```
Returns comprehensive pipeline status.

```
GET /api/pipeline/recommendations
```
Returns optimization recommendations.

```
GET /api/buckets
```
Returns lead bucket configurations.

```
GET /api/analytics
```
Returns detailed analytics data.

```
GET /api/stages
```
Returns available pipeline stages.

### Quality Control
```
POST /api/quality/check
```
Runs quality control check.

### Email Review
```
GET /api/review/list
```
Lists pending email reviews.

```
POST /api/review/action
Content-Type: application/json

{
  "campaignId": 123,
  "action": "send|ignore",
  "body": "Optional revised email body"
}
```

## Error Codes

- **400**: Bad Request (invalid input)
- **404**: Not Found
- **422**: Validation Error
- **429**: Rate Limit Exceeded
- **500**: Internal Server Error

## Logging

All API requests are logged with:
- HTTP method and path
- Client IP address
- User-Agent
- Response time
- Response size

Errors are logged with additional context for debugging.

## Examples

### Valid Request
```bash
curl -X GET "http://localhost:5000/api/stats" \
  -H "Content-Type: application/json"
```

### Invalid Request (Validation Error)
```bash
curl -X POST "http://localhost:5000/api/process/start" \
  -H "Content-Type: application/json" \
  -d '{"process": "invalid_process"}'
```

Response:
```json
{
  "error": true,
  "message": "Invalid process",
  "timestamp": "2026-01-29T14:46:54.552375",
  "path": "/api/process/start"
}
```

### Rate Limited Request
After exceeding the rate limit, responses will have HTTP status 429.

## Monitoring

Monitor logs for:
- High error rates
- Rate limiting violations
- Slow response times
- Security events

The API provides structured logging suitable for integration with monitoring systems.
