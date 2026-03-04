# GlobalAPI — Conventions & Rules

This document defines the rules, patterns, and conventions for the GlobalAPI project.
Any AI assistant (Claude Code, Codex, Copilot, etc.) or team member **must follow these rules** when contributing.

---

## 1. Layer Rules & Responsibilities

### 1.1 — `core/` Layer (Shared Foundation)

**Purpose:** Framework-level code that every module depends on. Not business logic.

**Rules:**
- NEVER import anything from `module/` — core knows nothing about business domains
- NEVER put business logic here — only infrastructure concerns
- Every class must be genuinely shared (used by 2+ modules). If only one module uses it, it belongs in that module
- Changes here affect ALL modules — require extra review
- Config classes are the ONLY place where framework annotations like `@EnableCaching`, `@EnableScheduling` live

**What belongs here:**
| Package | Contains | Example |
|---------|----------|---------|
| `core/api/` | API response wrappers, pagination | `ApiResponse.java`, `PageRequest.java` |
| `core/config/` | Spring configuration beans | `SecurityConfig.java`, `MyBatisConfig.java` |
| `core/exception/` | Global exception handling | `GlobalExceptionHandler.java`, `ErrorCode.java` |
| `core/security/` | Auth filters, JWT, API key | `JwtProvider.java`, `JwtAuthFilter.java` |

### 1.2 — `module/` Layer (Flat Feature Modules)

**Purpose:** Self-contained business features. Each module holds its own entity, service, controller, mapper, and DTOs together.

**Module structure:**
```
module/user/
├── User.java              # Entity (pure — no framework deps)
├── UserRole.java          # Enum
├── UserStatus.java        # Enum
├── UserMapper.java        # MyBatis mapper interface
├── UserService.java       # Business logic
├── UserController.java    # REST controller
├── dto/
│   ├── UserRequest.java   # Input DTO
│   └── UserResponse.java  # Output DTO
└── mapper/
    └── UserMapper.xml     # SP calls (also in resources/mapper/user/)
```

**Entity rules (within module):**
- ZERO framework dependencies — no Spring, no MyBatis, no Lombok `@Data` (use `@Getter`/`@Setter` only)
- Entities are **not** DTOs — they represent the real business object with behavior
- Domain entities CAN have validation logic (e.g., `User.isActive()`, `Course.hasHoles()`)
- Enums live next to their parent entity in the same module package
- NEVER expose domain entities directly in API responses

**Service rules (within module):**
- One service class per module (e.g., `UserService`, `CourseService`)
- When a service exceeds ~300 lines, split by responsibility (e.g., `UserQueryService`, `UserCommandService`)
- Services handle **transaction boundaries** (`@Transactional`)
- Services convert between domain entities and DTOs
- Cross-module calls go through the **other module's service**, never its mapper

**Cross-module dependency:**
```java
// ALLOWED — service to service
public class TournamentService {
    private final UserService userService;  // ✓
}

// FORBIDDEN — service to another module's mapper
public class TournamentService {
    private final UserMapper userMapper;    // ✗ never do this
}
```

**Controller rules (within module):**
- Controllers are **thin** — validate input, call service, return response. No business logic.
- One controller per module (or per aggregate root for sub-modules)
- Always return `ApiResponse<T>` — never return raw entities or plain objects
- Request/Response DTOs live in the module's `dto/` sub-package
- Use `@Valid` for input validation, never manual if-checks
- Path pattern: `/api/v1/{module-plural}/{resourceId}`
- Use `@Tag(name = "Module Name")` for Swagger grouping
- Never catch exceptions in controllers — let `GlobalExceptionHandler` handle them

**Controller naming conventions:**
| HTTP Method | Controller Method | Path |
|-------------|------------------|------|
| GET (list) | `list()` or `search()` | `/api/v1/users` |
| GET (one) | `getByUsrNo()` | `/api/v1/users/{usrNo}` |
| POST | `create()` | `/api/v1/users` |
| PUT | `update()` | `/api/v1/users/{usrNo}` |
| DELETE | `delete()` | `/api/v1/users/{usrNo}` |

**Mapper/Persistence rules (within module):**
- MyBatis `@Mapper` interfaces live in the module package
- Mapper XML files live in `resources/mapper/{module}/`
- ALL database access goes through stored procedures — no inline SQL in mapper XML
- SP naming convention: `sp_{module}_{action}` (e.g., `sp_user_find_by_usr_no`)
- NEVER expose MyBatis-specific types (like `SqlSession`) outside the module

**Stored Procedure XML pattern:**
```xml
<!-- ALWAYS use this pattern -->
<select id="findByUsrNo" statementType="CALLABLE" resultType="User">
    {CALL sp_user_find_by_usr_no(#{usrNo})}
</select>

<!-- NEVER use inline SQL -->
<select id="findByUsrNo" resultType="User">
    SELECT * FROM users WHERE usr_no = #{usrNo}  <!-- ✗ violates SP-only rule -->
</select>
```

---

## 2. DTO Strategy — Minimal & Effective

### 2.1 — DTO Layer Map

```
HTTP Request  →  Request DTO (adapter/in/web/dto/)
                      ↓
                  Service method
                      ↓  (converts to domain entity or command)
                  Domain Entity (domain/)
                      ↓
                  Service returns
                      ↓
              Response DTO (adapter/in/web/dto/)
                      ↓
              ApiResponse<ResponseDTO>  →  HTTP Response
```

### 2.2 — DTO Reuse Rules

**Rule: Create a new DTO only when the data shape is genuinely different.**

| Scenario | DTO Count | Approach |
|----------|-----------|----------|
| Create + Update have same fields | 1 Request DTO | Use `@Validated` with groups: `OnCreate.class`, `OnUpdate.class` |
| List vs Detail show different fields | 2 Response DTOs | `CourseListResponse` (summary) vs `CourseDetailResponse` (full) |
| Multiple APIs return same shape | 1 Response DTO | Reuse it. `UserResponse` works for getById, getMe, listUsers |
| Nested child objects | Separate DTO | `CourseHoleResponse` nested inside `CourseDetailResponse` |

**Validation groups example:**
```java
@Data
public class UserRequest {
    @NotBlank(groups = OnCreate.class)    // Required only on create
    private String username;

    @NotBlank(groups = OnCreate.class)    // Required only on create
    private String password;

    @Size(max = 50)                       // Always validated when present
    private String nickname;

    public interface OnCreate {}
    public interface OnUpdate {}
}
```

**Controller usage:**
```java
@PostMapping
public ApiResponse<UserResponse> create(@Validated(OnCreate.class) @RequestBody UserRequest req)

@PutMapping("/{usrNo}")
public ApiResponse<UserResponse> update(@Validated(OnUpdate.class) @RequestBody UserRequest req)
```

### 2.3 — DTO Naming Convention

| Type | Pattern | Example |
|------|---------|---------|
| Input (simple) | `{Entity}Request` | `UserRequest` |
| Input (search/filter) | `{Entity}SearchRequest` | `CourseSearchRequest` |
| Output (general) | `{Entity}Response` | `UserResponse` |
| Output (list summary) | `{Entity}ListResponse` | `CourseListResponse` |
| Output (full detail) | `{Entity}DetailResponse` | `CourseDetailResponse` |
| Output (nested child) | `{Child}Response` | `CourseHoleResponse` |
| Auth-specific | Descriptive name | `LoginRequest`, `TokenResponse` |

---

## 3. Module Expansion Rules

### 3.1 — When to Create a New Module

Create a new module under `module/` when:
- The feature has its **own data** (own tables/SPs)
- The feature has its **own API endpoints**
- The feature can be described in one sentence without mentioning another module
- The feature could **theoretically** run as a standalone service

### 3.2 — Module Growth Stages

```
Stage 1: Flat Module
module/user/
├── UserController.java
├── UserService.java
├── User.java
├── UserMapper.java
├── dto/
└── mapper/

    ↓ When: 3+ aggregate roots or controller > 10 endpoints

Stage 2: Sub-Modules
module/event/
├── common/              ← Shared enums, base classes within domain
├── tournament/
│   ├── TournamentController.java
│   ├── TournamentService.java
│   └── ...
├── league/
└── campaign/

    ↓ When: Sub-module exceeds 15+ files or needs its own database schema

Stage 3: Graduated Top-Level Module
module/tournament/       ← Promoted from event/tournament/
├── bracket/
├── scoring/
└── round/

    ↓ When: Module must run independently or be deployed separately

Stage 4: Extracted Microservice
New Spring Boot project, copies module/ folder + core/
```

### 3.3 — Module Checklist (for every new module)

Before considering a module complete:

- [ ] Entity classes in `module/{name}/`
- [ ] Enums in `module/{name}/` next to entity
- [ ] Stored procedures in `schema-h2.sql` with prefix `sp_{module}_`
- [ ] MyBatis mapper interface in `module/{name}/`
- [ ] Mapper XML in `resources/mapper/{name}/`
- [ ] Service class in `module/{name}/`
- [ ] Controller in `module/{name}/` with path `/api/v1/{module-plural}/`
- [ ] Request/Response DTOs in `module/{name}/dto/`
- [ ] Error codes added to `ErrorCode.java` with `{MODULE}_` prefix
- [ ] Swagger `@Tag` annotation on controller
- [ ] Seed data in `data-h2.sql` (if applicable)

---

## 4. Feature Design & Implementation Workflow

### 4.1 — Step-by-Step Workflow for New Features

```
Step 1: DESIGN          → Brainstorm & validate approach
Step 2: SCHEMA          → Tables, SPs, seed data
Step 3: DOMAIN          → Entities, repository interfaces
Step 4: PERSISTENCE     → MyBatis mapper + adapter
Step 5: SERVICE         → Business logic
Step 6: CONTROLLER      → REST endpoints
Step 7: SECURITY        → Auth rules, endpoint permissions
Step 8: VALIDATION      → Input validation, error codes
Step 9: DOCUMENTATION   → Swagger annotations
Step 10: TESTING        → Unit + integration tests
```

### 4.2 — Suggested Skills per Step

For team members using AI assistants (Claude Code, Codex, Copilot), use these skills at each step:

| Step | Activity | Suggested Skills |
|------|----------|-----------------|
| 1. Design | Requirements, architecture decisions | `brainstorming`, `domain-driven-design`, `architecture`, `concise-planning` |
| 2. Schema | Database design, stored procedures | `database-design`, `sql-pro`, `database` |
| 3. Domain | Entity modeling, interfaces | `java-pro`, `clean-code`, `ddd-tactical-patterns` |
| 4. Persistence | MyBatis mappers, XML config | `java-pro`, `sql-pro` |
| 5. Service | Business logic, transactions | `java-pro`, `clean-code`, `error-handling-patterns` |
| 6. Controller | REST endpoints, DTOs | `api-patterns`, `api-design-principles`, `java-pro` |
| 7. Security | Auth config, access control | `auth-implementation-patterns`, `api-security-best-practices`, `security-audit` |
| 8. Validation | Input validation, error handling | `error-handling-patterns`, `api-patterns` |
| 9. Docs | API documentation | `api-documentation`, `api-documenter` |
| 10. Testing | Unit, integration, API tests | `testing-patterns`, `test-driven-development`, `java-pro` |
| Review | Code review, quality check | `code-review-excellence`, `code-reviewer`, `clean-code`, `simplify` |
| Debug | Issue investigation | `debugging-toolkit-smart-debug`, `error-detective`, `systematic-debugging` |
| Refactor | Code improvement | `clean-code`, `code-refactoring-refactor-clean` |
| Security audit | Vulnerability check | `security-audit`, `security-scanning-security-sast`, `top-web-vulnerabilities` |
| Performance | Optimization | `performance-profiling`, `sql-optimization-patterns`, `database-optimizer` |
| Architecture review | Design validation | `architect-review`, `software-architecture`, `senior-architect` |

### 4.3 — Feature Branch Naming

```
feature/{module}/{short-description}
fix/{module}/{short-description}
refactor/{module}/{short-description}

Examples:
  feature/course/search-filters
  fix/auth/refresh-token-rotation
  refactor/user/split-query-command-service
```

---

## 5. Logging Conventions

### 5.1 — Logger Setup

```java
// Every class that logs: use Lombok
@Slf4j
@Service
public class UserService {
    // log is available automatically
}
```

### 5.2 — Log Level Rules

| Level | When to Use | Example |
|-------|-------------|---------|
| `ERROR` | Something failed that **should not happen**. Requires attention. | SP call failed, JWT signing error, unexpected null |
| `WARN` | Something unexpected but **handled gracefully**. Worth monitoring. | Expired refresh token used, rate limit approaching, deprecated API called |
| `INFO` | **Business events** that matter for operations. One per significant action. | User created, login success, course searched |
| `DEBUG` | **Developer context** for troubleshooting. Method entry/exit with params. | SP params, JWT claims parsed, filter chain step |
| `TRACE` | **Extremely detailed** flow. Rarely used. | Full request/response body, every iteration |

### 5.3 — Logging Patterns

**Pattern: Structured key-value format**
```java
// INFO — Business events (WHO did WHAT)
log.info("User created | usrNo={}, username={}", user.getUsrNo(), user.getUsername());
log.info("Login success | usrNo={}, loginType={}", usrNo, loginType);
log.info("Course search | filters={}, resultCount={}", searchRequest, count);

// WARN — Handled but unexpected
log.warn("Expired refresh token used | usrNo={}, tokenId={}", usrNo, tokenId);
log.warn("User not found for update | usrNo={}", usrNo);

// ERROR — Requires attention (always include exception)
log.error("SP call failed | sp=sp_user_find_by_usr_no, usrNo={}", usrNo, exception);
log.error("JWT validation failed | token={}", maskToken(token), exception);

// DEBUG — Developer context
log.debug("Calling SP | sp=sp_user_find_by_usr_no, params={usrNo: {}}", usrNo);
log.debug("Token generated | usrNo={}, expiresIn={}s", usrNo, expiresIn);
```

### 5.4 — Logging Rules

1. **NEVER log sensitive data:** passwords, full tokens, API keys, personal data
2. **Mask tokens:** show only last 8 chars → `...aBcDeFgH`
3. **Always include context IDs:** `usrNo`, `courseNo`, `tokenId` — so logs are traceable
4. **One INFO log per service method** — not per internal step
5. **ERROR must always include the exception object** as the last parameter
6. **Use parameterized logging** — `log.info("msg {}", var)`, NEVER `log.info("msg " + var)`
7. **No logging in domain entities** — entities are pure, no framework dependencies

### 5.5 — Module-Specific Log Prefixes

For easy grep/filtering in production:

```java
// Each module uses a consistent prefix in its log messages
log.info("[AUTH] Login success | usrNo={}", usrNo);
log.info("[USER] User created | usrNo={}", usrNo);
log.info("[COURSE] Course search | filters={}", filters);
log.info("[EVENT] Tournament created | tournamentNo={}", no);
```

### 5.6 — Request/Response Logging (Global)

Handled by a single interceptor in `core/config/`, not in individual controllers:

```java
// LoggingInterceptor — logs every request/response once
// INFO: method, path, status, duration
// DEBUG: headers (masked), request body
// ERROR: only if status >= 500
```

---

## 6. Error Handling Conventions

### 6.1 — ErrorCode Naming

```java
public enum ErrorCode {
    // Common
    INVALID_INPUT("C001", "Invalid input", HttpStatus.BAD_REQUEST),
    INTERNAL_ERROR("C999", "Internal server error", HttpStatus.INTERNAL_SERVER_ERROR),

    // Auth module — prefix AUTH_
    AUTH_INVALID_CREDENTIALS("A001", "Invalid credentials", HttpStatus.UNAUTHORIZED),
    AUTH_TOKEN_EXPIRED("A002", "Token expired", HttpStatus.UNAUTHORIZED),
    AUTH_REFRESH_TOKEN_INVALID("A003", "Invalid refresh token", HttpStatus.UNAUTHORIZED),
    AUTH_ACCESS_DENIED("A004", "Access denied", HttpStatus.FORBIDDEN),
    AUTH_API_KEY_INVALID("A005", "Invalid API key", HttpStatus.UNAUTHORIZED),

    // User module — prefix USER_
    USER_NOT_FOUND("U001", "User not found", HttpStatus.NOT_FOUND),
    USER_ALREADY_EXISTS("U002", "Username already exists", HttpStatus.CONFLICT),
    USER_INACTIVE("U003", "User account is inactive", HttpStatus.FORBIDDEN),

    // Course module — prefix COURSE_
    COURSE_NOT_FOUND("CS001", "Course not found", HttpStatus.NOT_FOUND),
    // ... add per module
}
```

### 6.2 — Exception Throwing Rules

```java
// In Service layer — throw BusinessException with ErrorCode
if (user == null) {
    throw new BusinessException(ErrorCode.USER_NOT_FOUND);
}

// In Controller — NEVER catch, let GlobalExceptionHandler handle it

// In Adapter — wrap infrastructure exceptions
try {
    return mapper.findByUsrNo(usrNo);
} catch (PersistenceException e) {
    log.error("[USER] SP call failed | usrNo={}", usrNo, e);
    throw new BusinessException(ErrorCode.INTERNAL_ERROR, e);
}
```

---

## 7. Stored Procedure Conventions

### 7.1 — Naming

```
sp_{module}_{action}

Actions:
  create, find_by_{field}, update, delete, list, search, count

Examples:
  sp_user_create
  sp_user_find_by_usr_no
  sp_user_find_by_username
  sp_user_update
  sp_user_delete
  sp_user_list
  sp_course_search
  sp_course_find_by_no
  sp_auth_create_refresh_token
```

### 7.2 — SP Design Rules

- Every SP returns a result (even delete/update returns affected row count)
- List/Search SPs accept `p_page` and `p_size` parameters for pagination
- List/Search SPs return total count via OUT parameter or separate count SP
- SPs handle soft delete (set `status = 'INACTIVE'`), never hard delete in application code
- Parameter prefix: `p_` to distinguish from column names

### 7.3 — H2 Stored Procedure Pattern

```sql
-- H2 uses CREATE ALIAS for stored procedures
CREATE ALIAS IF NOT EXISTS sp_user_find_by_usr_no AS $$
ResultSet spUserFindByUsrNo(Connection conn, Long pUsrNo) throws SQLException {
    PreparedStatement ps = conn.prepareStatement(
        "SELECT usr_no, username, nickname, role, status, created_at, updated_at " +
        "FROM users WHERE usr_no = ? AND status != 'DELETED'"
    );
    ps.setLong(1, pUsrNo);
    return ps.executeQuery();
}
$$;
```

---

## 8. API Design Conventions

### 8.1 — URL Structure

```
/api/v{version}/{module}/{resource}/{sub-resource}

Examples:
  /api/v1/auth/login
  /api/v1/users
  /api/v1/users/{usrNo}
  /api/v1/users/me
  /api/v1/courses
  /api/v1/courses/{courseNo}
  /api/v1/courses/popular
  /api/v1/events/tournaments
  /api/v1/events/tournaments/{tournamentNo}/brackets
```

### 8.2 — Response Format (Always)

```json
{
    "code": "SUCCESS",
    "message": "OK",
    "data": { ... },
    "timestamp": "2026-03-04T12:00:00Z"
}
```

Error response:
```json
{
    "code": "U001",
    "message": "User not found",
    "data": null,
    "timestamp": "2026-03-04T12:00:00Z"
}
```

Paginated response:
```json
{
    "code": "SUCCESS",
    "message": "OK",
    "data": {
        "items": [ ... ],
        "page": 1,
        "size": 20,
        "totalItems": 150,
        "totalPages": 8
    },
    "timestamp": "2026-03-04T12:00:00Z"
}
```

### 8.3 — HTTP Status Code Usage

| Status | When |
|--------|------|
| 200 | Successful GET, PUT, DELETE |
| 201 | Successful POST (resource created) |
| 400 | Validation error, malformed request |
| 401 | Missing or invalid authentication |
| 403 | Authenticated but not authorized |
| 404 | Resource not found |
| 409 | Conflict (duplicate username, etc.) |
| 500 | Unexpected server error |

---

## 9. Security Conventions

### 9.1 — Endpoint Security Matrix

| Pattern | Auth Required | Notes |
|---------|--------------|-------|
| `/api/v1/auth/login` | No | Public |
| `/api/v1/auth/refresh` | No | Public (refresh token in body) |
| `/api/v1/users` POST | No | Public registration |
| `/api/v1/**/admin/**` | JWT + ADMIN role | Admin-only paths |
| `/api/v1/**` | JWT or X-API-KEY | All other endpoints |
| `/swagger-ui/**` | No | Dev only (disable in prod profile) |
| `/actuator/health` | No | Health check |
| `/actuator/**` | JWT + ADMIN role | Other actuator endpoints |

### 9.2 — Resource Ownership

```java
// Users can only modify their own data unless ADMIN
@PutMapping("/{usrNo}")
@PreAuthorize("@securityUtil.isOwnerOrAdmin(#usrNo)")
public ApiResponse<UserResponse> update(@PathVariable Long usrNo, ...) { }
```

### 9.3 — Internal Service Calls (x-api-key)

```properties
# application.properties
app.security.api-keys[0].name=scoring-service
app.security.api-keys[0].key=sk-scoring-xxxx
app.security.api-keys[1].name=notification-service
app.security.api-keys[1].key=sk-notif-xxxx
```

Internal calls bypass JWT but receive role `INTERNAL` — which can access all endpoints except admin management.

---

## 10. Testing Conventions

### 10.1 — Test Structure

```
src/test/java/com/golfzon/globalapi/
├── module/
│   ├── auth/
│   │   ├── AuthControllerTest.java      # MockMvc integration test
│   │   └── AuthServiceTest.java         # Unit test
│   ├── user/
│   │   ├── UserControllerTest.java
│   │   ├── UserServiceTest.java
│   │   └── UserMapperTest.java          # SP execution test with H2
│   └── course/
└── core/
    └── security/
        └── JwtProviderTest.java
```

### 10.2 — Test Naming

```java
@Test
void shouldReturnUserWhenUsrNoExists() { }

@Test
void shouldThrowUserNotFoundWhenUsrNoInvalid() { }

@Test
void shouldReturn401WhenTokenExpired() { }
```

Pattern: `should{ExpectedResult}When{Condition}`

### 10.3 — Test Data

- Use `data-h2.sql` for shared seed data (admin user, sample courses)
- Each test class can use `@Sql` to load module-specific test data
- Never depend on test execution order

---

## 11. Code Style Quick Reference

| Item | Convention |
|------|-----------|
| Package names | lowercase, singular (`module.user`, not `modules.users`) |
| Class names | PascalCase, noun (`UserService`, `CourseController`) |
| Method names | camelCase, verb (`createUser`, `findByUsrNo`) |
| Constants | UPPER_SNAKE (`MAX_LOGIN_ATTEMPTS`) |
| DB columns | lower_snake (`usr_no`, `created_at`) |
| SP names | lower_snake with prefix (`sp_user_create`) |
| API paths | kebab-case plural (`/api/v1/courses/most-played`) |
| DTO fields | camelCase, matching JSON keys (`usrNo`, `createdAt`) |
| Lombok | `@Getter`/`@Setter` on entities, `@Data` on DTOs only, `@RequiredArgsConstructor` on services |
| Null handling | Return `Optional<>` from repository find methods, throw `BusinessException` in service |

---

## 12. Transaction Conventions

### 12.1 — `@Transactional` Usage

```java
// Read-only operations — use readOnly for performance optimization
@Transactional(readOnly = true)
public UserResponse getUserByUsrNo(Long usrNo) { ... }

@Transactional(readOnly = true)
public PageResponse<CourseListResponse> searchCourses(CourseSearchRequest req) { ... }

// Write operations — default @Transactional (readOnly = false)
@Transactional
public UserResponse createUser(UserRequest req) { ... }

@Transactional
public void deleteUser(Long usrNo) { ... }
```

### 12.2 — Transaction Rules

- `@Transactional` goes on **service methods**, never on controllers or mappers
- Use `readOnly = true` for all GET/query operations — enables DB read replicas and optimization
- Use default `@Transactional` (readOnly = false) for all write operations (POST, PUT, DELETE)
- If a method does both read and write, use default `@Transactional`
- NEVER put `@Transactional` on private methods — Spring proxies don't intercept them
- For cross-module calls, the **outermost service** owns the transaction boundary

---

## 13. Date/Time Conventions

### 13.1 — Rules

- Use `java.time.LocalDateTime` for all date/time fields in entities and DTOs
- Store all timestamps in **UTC** in the database
- DB column type: `TIMESTAMP` (not `DATETIME`)
- JSON serialization format: **ISO 8601** — `"2026-03-04T12:00:00Z"`
- Configure globally in `application.properties`:
  ```properties
  spring.jackson.serialization.write-dates-as-timestamps=false
  spring.jackson.time-zone=UTC
  ```
- Timezone conversion happens on the **client side**, never in the API
- Use `Instant` only when you need machine-to-machine timestamps (e.g., token expiry)
- Entity fields: `createdAt`, `updatedAt` (camelCase, matching JSON output)
- DB columns: `created_at`, `updated_at` (snake_case)

---

## 14. Pagination Conventions

### 14.1 — Defaults

| Parameter | Default | Maximum | Notes |
|-----------|---------|---------|-------|
| `page` | 1 | - | 1-based (not 0-based) |
| `size` | 20 | 100 | Enforce max in `PageRequest` validation |
| `sort` | `created_at DESC` | - | Module can override default sort |

### 14.2 — PageRequest (shared in core/)

```java
@Data
public class PageRequest {
    @Min(1)
    private int page = 1;

    @Min(1) @Max(100)
    private int size = 20;

    private String sort;

    // Convenience: calculate offset for SP
    public int getOffset() {
        return (page - 1) * size;
    }
}
```

### 14.3 — PageResponse (shared in core/)

```java
@Data
@Builder
public class PageResponse<T> {
    private List<T> items;
    private int page;
    private int size;
    private long totalItems;
    private int totalPages;
}
```

### 14.4 — SP Pagination Pattern

Stored procedures receive `p_offset` and `p_size` (not page number):
```sql
-- SP receives offset calculated by Java, not page number
CREATE ALIAS IF NOT EXISTS sp_user_list AS $$
ResultSet spUserList(Connection conn, Integer pOffset, Integer pSize) throws SQLException {
    PreparedStatement ps = conn.prepareStatement(
        "SELECT * FROM users WHERE status != 'DELETED' ORDER BY created_at DESC LIMIT ? OFFSET ?"
    );
    ps.setInt(1, pSize);
    ps.setInt(2, pOffset);
    return ps.executeQuery();
}
$$;
```

---

## 15. Code Review Checklist

Use this checklist when reviewing source code — whether reviewing existing code, PR changes, or AI-generated code.
Reference the section numbers from this document for each check.

### 15.1 — Layer & Module Violation Checks (Section 1)

| Check | Violation | Severity |
|-------|-----------|----------|
| Does `core/` import from `module/`? | Section 1.1 | **BLOCKER** |
| Does an entity import Spring/MyBatis/Lombok `@Data`? | Section 1.2 | **BLOCKER** |
| Does a controller contain business logic? | Section 1.2 | **HIGH** |
| Does a service call another module's mapper directly? | Section 1.2 | **BLOCKER** |
| Does an entity have `@Select`, `@Mapper`, or any SQL? | Section 1.2 | **BLOCKER** |
| Does mapper XML use inline SQL instead of SP call? | Section 1.2 | **HIGH** |
| Is a domain entity returned directly in an API response? | Section 1.2 | **HIGH** |
| Does a controller catch exceptions instead of letting GlobalExceptionHandler handle them? | Section 1.2 | **MEDIUM** |

### 15.2 — DTO Checks (Section 2)

| Check | What to Look For |
|-------|-----------------|
| DTO explosion? | Are there multiple DTOs with the same shape? Consolidate with validation groups. |
| Wrong location? | Request/Response DTOs must be in the module's `dto/` sub-package. |
| Missing `@Valid`/`@Validated`? | All request body inputs must be validated. |
| Domain entity as response? | Never. Always map to a Response DTO. |
| Naming convention? | Must follow `{Entity}Request`, `{Entity}Response`, `{Entity}SearchRequest` pattern. |

### 15.3 — Stored Procedure Checks (Section 7)

| Check | What to Look For |
|-------|-----------------|
| SP naming follows `sp_{module}_{action}`? | e.g., `sp_user_find_by_usr_no`, not `getUserById` |
| Parameters prefixed with `p_`? | e.g., `p_usr_no`, not `usrNo` |
| SP returns a result? | Even delete/update must return affected count |
| Mapper XML uses `statementType="CALLABLE"`? | Required for SP calls |
| No inline SQL in mapper XML? | All queries must go through SP |

### 15.4 — Security Checks (Section 9)

| Check | What to Look For |
|-------|-----------------|
| New endpoint added to SecurityConfig? | Public endpoints must be explicitly permitted. All others default to JWT required. |
| Resource ownership enforced? | Write endpoints must check `@PreAuthorize("@securityUtil.isOwnerOrAdmin(#usrNo)")` |
| Sensitive data in response? | Password, tokens, API keys must NEVER appear in response DTOs |
| usrNo used (not username) for operations? | All feature APIs use usrNo, never username |

### 15.5 — Logging Checks (Section 5)

| Check | What to Look For |
|-------|-----------------|
| Sensitive data logged? | Passwords, full tokens, API keys must never be logged. Mask tokens. |
| Module prefix used? | `[AUTH]`, `[USER]`, `[COURSE]` etc. |
| Parameterized logging? | `log.info("msg {}", var)` not `log.info("msg " + var)` |
| ERROR includes exception? | `log.error("msg", exception)` — exception must be last param |
| Logging in entity? | NEVER. Entities are pure, no framework dependencies. |

### 15.6 — API Consistency Checks (Section 8)

| Check | What to Look For |
|-------|-----------------|
| Response wrapped in `ApiResponse<T>`? | Every controller method must return `ApiResponse`. |
| URL follows pattern? | `/api/v1/{module-plural}/{id}` |
| HTTP status codes correct? | POST → 201, GET/PUT/DELETE → 200 |
| Error codes added? | New module must have its own prefix in `ErrorCode.java` |
| Swagger `@Tag` present? | Every controller must have `@Tag(name = "Module Name")` |

### 15.7 — Transaction Checks (Section 12)

| Check | What to Look For |
|-------|-----------------|
| `@Transactional` on service, not controller? | Transaction boundary must be in service layer |
| `readOnly = true` for query methods? | GET/search operations should use `@Transactional(readOnly = true)` |
| `@Transactional` on private method? | NEVER — Spring proxies don't intercept private methods |

### 15.8 — Date/Time Checks (Section 13)

| Check | What to Look For |
|-------|-----------------|
| Using `java.time.LocalDateTime`? | Not `java.util.Date` or `java.sql.Timestamp` |
| Timestamps in UTC? | No timezone-specific values stored in DB |
| ISO 8601 format in JSON? | `"2026-03-04T12:00:00Z"`, not epoch or custom format |

### 15.9 — Pagination Checks (Section 14)

| Check | What to Look For |
|-------|-----------------|
| Page size capped at 100? | `@Max(100)` on size parameter |
| 1-based page number? | Page starts at 1, not 0 |
| SP receives offset, not page? | Java calculates `(page - 1) * size`, SP gets offset |

### 15.10 — Module Completeness Check (Section 3.3)

When reviewing a new module, verify the full checklist from Section 3.3 is satisfied:
entity, enums, SPs, mapper interface, mapper XML, service, controller, DTOs, error codes, swagger tag, seed data.

### 15.11 — Review Severity Levels

| Severity | Action | Examples |
|----------|--------|----------|
| **BLOCKER** | Must fix before merge. Violates architecture boundary. | Layer violation, entity with framework deps, cross-module mapper call |
| **HIGH** | Must fix. Breaks conventions, causes maintenance debt. | Inline SQL, missing validation, business logic in controller |
| **MEDIUM** | Should fix. Inconsistency or missing best practice. | Wrong DTO name, missing log prefix, missing swagger tag |
| **LOW** | Nice to have. Style or minor improvement. | Log message wording, variable naming preference |

### 15.12 — When to Update Conventions

This document should be updated when:
- A new pattern emerges that 2+ modules follow (document it as a convention)
- A code review catches a recurring issue not covered here (add it as a check)
- A decision from the Decision Log changes how code should be structured
- A new module type is introduced (e.g., async/event-driven) with its own rules

**Who updates:** The reviewer who identifies the gap creates a PR to add it.
**Format:** Add the convention with a code example (good/bad), then add a corresponding review check to Section 15.
