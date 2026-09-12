# API Reference

<cite>
**Referenced Files in This Document**
- [main.py](file://src/api/main.py)
- [schemas.py](file://src/api/schemas.py)
- [middleware.py](file://src/api/middleware.py)
- [rate_limit.py](file://src/api/rate_limit.py)
- [config.py](file://src/api/config.py)
- [dependencies.py](file://src/api/dependencies.py)
- [auth.py](file://src/api/routers/auth.py)
- [query.py](file://src/api/routers/query.py)
- [status.py](file://src/api/routers/status.py)
- [approvals.py](file://src/api/routers/approvals.py)
- [appointments_crud.py](file://src/api/routers/appointments_crud.py)
- [medications_crud.py](file://src/api/routers/medications_crud.py)
- [audit.py](file://src/api/routers/audit.py)
- [health.py](file://src/api/routers/health.py)
- [alerts.py](file://src/api/routers/alerts.py)
- [deliveries.py](file://src/api/routers/deliveries.py)
- [__init__.py](file://src/api/routers/__init__.py)
- [supervisor_agent.py](file://src/agents/supervisor_agent.py)
- [schemas.py](file://src/models/schemas.py)
- [audit_log.py](file://src/models/audit_log.py)
- [escalation_logic.py](file://src/models/escalation_logic.py)
- [communication_tools.py](file://src/tools/communication_tools.py)
- [retry.py](file://src/tools/retry.py)
- [architecture.md](file://architecture.md)
- [AGENTS.md](file://AGENTS.md)
</cite>

## Update Summary
**Changes Made**
- Added comprehensive FastAPI REST API documentation with authentication endpoints
- Documented CRUD operations for appointments and medications
- Added audit logging, health monitoring, and middleware documentation
- Included CORS, rate limiting, and request ID tracking details
- Updated API structure to reflect the new router-based architecture
- Enhanced authentication and authorization requirements section

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Authentication and Authorization](#authentication-and-authorization)
7. [Rate Limiting and Security](#rate-limiting-and-security)
8. [Health Monitoring](#health-monitoring)
9. [Client Implementation Guidelines](#client-implementation-guidelines)
10. [Performance Considerations](#performance-considerations)
11. [Troubleshooting Guide](#troubleshooting-guide)
12. [Conclusion](#conclusion)
13. [Appendices](#appendices)

## Introduction
CareBridge provides a comprehensive FastAPI REST API for system interaction, built on top of the existing Supervisor Agent functionality. The API exposes programmatic endpoints for care coordination, including event processing, caregiver Q&A interactions, human approval workflows, and operational CRUD operations for appointments and medications.

The API follows modern REST principles with JWT authentication, comprehensive audit logging, health monitoring, and robust error handling. All endpoints are documented through OpenAPI/Swagger at `/docs` endpoint.

**Updated** Added complete FastAPI REST API layer with authentication, CRUD operations, and middleware infrastructure while maintaining backward compatibility with existing Supervisor Agent functions.

## Project Structure
CareBridge's API is organized as a modular FastAPI application with clear separation of concerns:

```mermaid
graph TB
Client["Client Applications"]
Main["FastAPI App<br/>create_app()"]
Middleware["Middleware Stack<br/>RequestID, CORS, Rate Limit"]
Routers["API Routers<br/>Auth, Query, Status, CRUD"]
Dependencies["Dependencies<br/>User Auth, Supervisor"]
Schemas["Pydantic Models<br/>Request/Response Types"]
Audit["Audit Trail<br/>Immutable SQLite"]
Client --> Main
Main --> Middleware
Middleware --> Routers
Routers --> Dependencies
Routers --> Schemas
Routers --> Audit
```

**Diagram sources**
- [main.py:77-120](file://src/api/main.py#L77-L120)
- [__init__.py:24-39](file://src/api/routers/__init__.py#L24-L39)
- [middleware.py:121-168](file://src/api/middleware.py#L121-L168)

**Section sources**
- [main.py:1-125](file://src/api/main.py#L1-L125)
- [__init__.py:1-42](file://src/api/routers/__init__.py#L1-L42)

## Core Components
The API surface consists of several key components that work together to provide comprehensive care coordination capabilities:

### Authentication Endpoints
- `POST /auth/login` - Exchange credentials for access/refresh token pair
- `POST /auth/refresh` - Refresh expired access tokens
- `GET /auth/me` - Get current authenticated user information
- `POST /auth/firebase/exchange` - Exchange Firebase ID token for CareBridge JWTs
- `GET /auth/firebase/config` - Check if Firebase authentication is enabled

### Care Coordination Endpoints
- `POST /query` - Natural language Q&A backed by Supervisor Agent
- `GET /status/{care_recipient_id}` - Synthesized status summary
- `GET /approvals` - Pending action queue for human review
- `POST /approvals/{action_id}/approve` - Approve pending actions
- `POST /approvals/{action_id}/reject` - Reject pending actions

### Operational CRUD Endpoints
- **Appointments**: Full CRUD operations under `/care-recipients/me/appointments`
- **Medications**: Full CRUD operations under `/care-recipients/me/medications`
- **Settings**: User preferences management under `/settings/me`

### Monitoring and Health
- `GET /health` - Liveness probe
- `GET /ready` - Readiness check with dependency validation
- `GET /version` - Build metadata and version information
- `GET /audit` - Paginated audit trail with filtering

**Section sources**
- [auth.py:60-140](file://src/api/routers/auth.py#L60-L140)
- [query.py:22-56](file://src/api/routers/query.py#L22-L56)
- [status.py:21-37](file://src/api/routers/status.py#L21-L37)
- [approvals.py:36-134](file://src/api/routers/approvals.py#L36-L134)
- [appointments_crud.py:57-240](file://src/api/routers/appointments_crud.py#L57-L240)
- [medications_crud.py:55-239](file://src/api/routers/medications_crud.py#L55-L239)
- [health.py:75-142](file://src/api/routers/health.py#L75-L142)

## Architecture Overview
CareBridge implements a layered architecture with clear separation between presentation (FastAPI), business logic (Supervisor Agent), and data persistence (SQLite with immutable audit trail).

```mermaid
sequenceDiagram
participant C as "Client"
participant F as "FastAPI"
participant M as "Middleware"
participant A as "Auth"
participant S as "Supervisor"
participant D as "Database"
C->>F : HTTP Request
F->>M : Apply Middleware
M->>A : Validate JWT Token
A-->>M : User Context
M->>S : Route to Handler
S->>D : Read/Write Data
D-->>S : Results
S-->>F : Business Logic Result
F-->>C : JSON Response
Note over M,D : All mutations write audit events first
```

**Diagram sources**
- [main.py:101-118](file://src/api/main.py#L101-L118)
- [dependencies.py:42-84](file://src/api/dependencies.py#L42-L84)
- [audit.py:22-58](file://src/api/routers/audit.py#L22-L58)

## Detailed Component Analysis

### Authentication System
The authentication system supports both traditional email/password and Firebase integration:

**JWT Authentication Flow:**
1. Client sends credentials to `/auth/login`
2. Server validates against stored user database
3. Returns access token (15 min) and refresh token (7 days)
4. Subsequent requests include `Authorization: Bearer <token>` header

**Firebase Integration:**
- Hybrid identity model supporting Google sign-in
- Exchanges Firebase ID tokens for CareBridge JWTs
- Automatic user provisioning and care recipient assignment
- Custom tokens for client-side Firebase SDK usage

**Security Features:**
- Rate limiting on auth endpoints (60/min default)
- Constant-time password comparison
- Secure token storage and rotation
- Role-based access control (RBAC)

**Section sources**
- [auth.py:60-140](file://src/api/routers/auth.py#L60-L140)
- [auth.py:163-320](file://src/api/routers/auth.py#L163-L320)
- [dependencies.py:42-84](file://src/api/dependencies.py#L42-L84)

### Care Coordination API
The core care coordination functionality is exposed through two main endpoints:

**Query Endpoint (`POST /query`):**
- Accepts natural language questions about care recipients
- Routes to Supervisor Agent for intelligent response generation
- Returns synthesized answers based on recent audit events and pending actions
- Graceful degradation when LLM runtime is unavailable (HTTP 503)

**Status Endpoint (`GET /status/{care_recipient_id}`):**
- Provides deterministic status summaries without LLM dependency
- Uses `synthesize_status()` tool for consistent results
- Returns structured `StatusSummary` with text, events, and pending actions

**Error Handling:**
- LLM-dependent routes return 503 with detailed reason when runtime unavailable
- Validation errors return 422 with field-specific messages
- Unknown recipients return 404 with appropriate error messages

**Section sources**
- [query.py:22-56](file://src/api/routers/query.py#L22-L56)
- [status.py:21-37](file://src/api/routers/status.py#L21-L37)
- [supervisor_agent.py:398-429](file://src/agents/supervisor_agent.py#L398-L429)

### Human Approval Workflow
The approval system enables human-in-the-loop decision making for sensitive operations:

**Approval Queue (`GET /approvals`):**
- Lists all pending actions requiring human review
- Supports filtering by care recipient
- Returns `PendingAction` models with full context

**Decision Endpoints:**
- `POST /approvals/{action_id}/approve` - Approve pending action
- `POST /approvals/{action_id}/reject` - Reject pending action
- Both require caregiver role permissions
- Optional reason field logged for audit purposes

**Workflow Integration:**
- Decisions trigger Supervisor Agent re-dispatch for approved actions
- Rejections log completion without further action
- All decisions create immutable audit trail entries

**Section sources**
- [approvals.py:36-134](file://src/api/routers/approvals.py#L36-L134)
- [supervisor_agent.py:432-593](file://src/agents/supervisor_agent.py#L432-L593)

### CRUD Operations
Comprehensive CRUD operations for operational data management:

**Appointments Management:**
- Full CRUD operations with validation
- Future appointment date enforcement
- Status management (scheduled, cancelled, completed)
- Audit trail for all modifications

**Medications Management:**
- Medication lifecycle management
- Refill threshold configuration
- Pharmacy integration support
- Soft delete functionality

**Data Isolation:**
- All operations scoped to authenticated user's care recipient
- Cross-user access returns 404 (not 403) for security
- Care recipient assignment required for access

**Section sources**
- [appointments_crud.py:57-240](file://src/api/routers/appointments_crud.py#L57-L240)
- [medications_crud.py:55-239](file://src/api/routers/medications_crud.py#L55-L239)

## Authentication and Authorization

### JWT Authentication
All protected endpoints require valid JWT tokens in the `Authorization: Bearer` header:

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

**Token Lifecycle:**
- Access tokens: 15-minute expiration
- Refresh tokens: 7-day expiration
- Automatic token refresh via `/auth/refresh`

### Role-Based Access Control (RBAC)
Three predefined roles with specific permissions:

| Role | Permissions |
|------|-------------|
| `viewer` | Read-only access to status and audit trails |
| `caregiver_secondary` | Full CRUD + approve/reject actions |
| `caregiver_primary` | All permissions including user management |

### Firebase Integration
Optional Firebase authentication for hybrid identity:

```python
# Exchange Firebase ID token for CareBridge JWTs
response = await client.post("/auth/firebase/exchange", json={
    "id_token": firebase_id_token
})
```

**Features:**
- Automatic user provisioning from Firebase profile
- Care recipient assignment during onboarding
- Custom tokens for client-side Firebase SDK
- Seamless migration from password-based auth

**Section sources**
- [auth.py:60-140](file://src/api/routers/auth.py#L60-L140)
- [auth.py:163-320](file://src/api/routers/auth.py#L163-L320)
- [dependencies.py:87-109](file://src/api/dependencies.py#L87-L109)

## Rate Limiting and Security

### Rate Limiting Strategy
Two-tier rate limiting protects API resources:

| Endpoint Type | Default Limit | Purpose |
|---------------|---------------|---------|
| Global | 300 requests/minute | Protect overall API capacity |
| Auth | 60 requests/minute | Prevent brute force attacks |

**Implementation:**
- IP-based rate limiting using `slowapi`
- Configurable limits via environment variables
- Graceful 429 responses with `Retry-After` headers

### Request Security
Comprehensive security measures protect API integrity:

**Request Validation:**
- Pydantic v2 models enforce strict schema validation
- Field-level constraints (length, format, range)
- Custom validators for complex business rules

**Input Sanitization:**
- Maximum request body size: 1MB (configurable)
- Email format validation
- Timezone-aware datetime parsing
- IANA timezone validation

**Output Protection:**
- No PII in logs or error responses
- Structured error envelopes with request correlation
- Stack traces never exposed to clients

### CORS Configuration
Cross-Origin Resource Sharing configured for web applications:

```python
# Default configuration allows localhost:3000
CORS_ORIGINS=http://localhost:3000
```

**Features:**
- Configurable allowed origins
- Credential support for cookie-based auth
- Method and header whitelisting

**Section sources**
- [rate_limit.py:1-42](file://src/api/rate_limit.py#L1-L42)
- [middleware.py:121-168](file://src/api/middleware.py#L121-L168)
- [config.py:106-110](file://src/api/config.py#L106-L110)

## Health Monitoring

### Health Check Endpoints
Three levels of health monitoring ensure system reliability:

**Liveness Probe (`GET /health`):**
- Simple availability check
- Returns `{"status": "ok"}` when server responds
- Used by container orchestrators for restart decisions

**Readiness Probe (`GET /ready`):**
- Validates critical dependencies
- Checks audit database connectivity
- Verifies MCP registry loading
- Reports LLM provider status and availability
- Returns HTTP 503 with degraded status when dependencies fail

**Version Information (`GET /version`):**
- Application metadata for debugging
- Git commit SHA and build timestamp
- Environment identification

### Dependency Monitoring
The readiness endpoint performs non-blocking checks:

```python
checks = {
    "audit_db": True,      # SQLite audit trail accessible
    "mcp_registry": True,  # Model Context Protocol loaded
    "llm_provider": "gemini", # Resolved provider name
    "llm_available": True   # Provider can build adapter
}
```

**Graceful Degradation:**
- Missing LLM credentials don't affect service readiness
- Individual routes return 503 when their dependencies are unavailable
- Deterministic fallback paths available for LLM-dependent features

**Section sources**
- [health.py:75-142](file://src/api/routers/health.py#L75-L142)
- [config.py:284-336](file://src/api/config.py#L284-L336)

## Client Implementation Guidelines

### Basic Authentication Flow
```python
import httpx

async def authenticate():
    async with httpx.AsyncClient() as client:
        # Login to get tokens
        response = await client.post(
            "http://localhost:8000/auth/login",
            json={"email": "user@example.com", "password": "password"}
        )
        
        tokens = response.json()
        access_token = tokens["access_token"]
        refresh_token = tokens["refresh_token"]
        
        # Use access token for API calls
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await client.get(
            "http://localhost:8000/care-recipients/me/appointments",
            headers=headers
        )
```

### Error Handling Pattern
```python
async def handle_api_call(client, endpoint, data):
    try:
        response = await client.post(endpoint, json=data)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            # Handle token refresh
            await refresh_tokens()
            return await handle_api_call(client, endpoint, data)
        elif e.response.status_code == 429:
            # Respect retry-after header
            retry_after = int(e.response.headers.get("Retry-After", 60))
            await asyncio.sleep(retry_after)
            return await handle_api_call(client, endpoint, data)
        else:
            raise
```

### Pagination for Large Datasets
```python
async def fetch_all_audit_events():
    events = []
    page = 1
    page_size = 50
    
    while True:
        response = await client.get(
            "/audit",
            params={"page": page, "page_size": page_size}
        )
        data = response.json()
        events.extend(data["items"])
        
        if page >= data["pages"]:
            break
        page += 1
    
    return events
```

**Section sources**
- [auth.py:60-88](file://src/api/routers/auth.py#L60-L88)
- [audit.py:22-58](file://src/api/routers/audit.py#L22-L58)

## Performance Considerations

### Database Optimization
- SQLite connections opened per-call to avoid contention
- Immutable audit trail ensures read consistency
- Connection pooling recommended for high-throughput deployments

### Caching Strategy
- Settings cached with `lru_cache` for performance
- User lookups offloaded to thread pool to prevent blocking
- Audit queries optimized with pagination

### Memory Management
- Request body size limited to 1MB by default
- Streaming responses for large datasets
- Proper resource cleanup in exception handlers

### Concurrency
- Async/await throughout the stack for high concurrency
- Thread pool for blocking operations (SQLite, external APIs)
- Rate limiting prevents resource exhaustion

## Troubleshooting Guide

### Common Authentication Issues
- **401 Unauthorized**: Invalid or expired JWT token
- **403 Forbidden**: Insufficient role permissions
- **422 Unprocessable Entity**: Invalid request payload

### API Error Patterns
All errors follow a consistent envelope format:

```json
{
    "error": "Human-readable error message",
    "request_id": "unique-request-id",
    "details": [...] // For validation errors
}
```

### Debugging Techniques
- Use `X-Request-ID` header for request correlation
- Check audit trail for operation history
- Monitor `/ready` endpoint for dependency status
- Enable debug logging with `LOG_LEVEL=DEBUG`

### Performance Issues
- Monitor rate limit headers for throttling
- Check database query performance in audit trail
- Profile slow endpoints with request timing logs

**Section sources**
- [middleware.py:171-245](file://src/api/middleware.py#L171-L245)
- [audit.py:22-58](file://src/api/routers/audit.py#L22-L58)

## Conclusion
CareBridge's FastAPI REST API provides a comprehensive, secure, and scalable interface for care coordination systems. The API combines the power of the existing Supervisor Agent with modern REST principles, offering:

- **Complete Authentication**: JWT-based with Firebase integration
- **Rich Functionality**: CRUD operations, Q&A, approvals, and monitoring
- **Robust Security**: Rate limiting, input validation, and RBAC
- **Operational Excellence**: Health monitoring, audit trails, and graceful degradation
- **Developer Experience**: Comprehensive documentation and consistent error handling

The API maintains backward compatibility with existing Supervisor Agent functions while providing a modern REST interface for new integrations.

## Appendices

### API Versioning Strategy
The API uses semantic versioning with the following approach:
- Major versions indicate breaking changes
- Minor versions add new endpoints/features
- Patch versions fix bugs without changing behavior
- Current version: 1.0.0 (as defined in settings)

### Backwards Compatibility Guarantees
- New optional fields added to request/response models
- Deprecated endpoints return warnings but continue working
- Enum values only appended, never removed
- Error codes remain stable across minor versions

### Environment Configuration
Key environment variables for deployment:

```bash
# Application
APP_NAME="CareBridge API"
APP_VERSION="1.0.0"
ENVIRONMENT="production"

# Security
JWT_SECRET_KEY="your-secret-key-here"
BCRYPT_ROUNDS="12"

# Rate Limiting
GLOBAL_RATE_LIMIT="300/minute"
AUTH_RATE_LIMIT="60/minute"

# CORS
CORS_ORIGINS="http://localhost:3000,https://app.carebridge.com"

# Database
AUTH_DB_PATH="/data/auth.db"
AUDIT_DB_PATH="/data/audit.db"

# Logging
JSON_LOGGING="true"
LOG_LEVEL="INFO"
```

### Testing Guidelines
- Use test database isolation for each test suite
- Mock external dependencies (LLM providers, Firebase)
- Test authentication flows with test users
- Validate rate limiting behavior with concurrent requests
- Verify audit trail completeness for all operations

**Section sources**
- [config.py:48-358](file://src/api/config.py#L48-L358)
- [main.py:65-70](file://src/api/main.py#L65-L70)