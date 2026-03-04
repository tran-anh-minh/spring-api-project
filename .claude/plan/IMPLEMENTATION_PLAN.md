# GlobalAPI — Implementation Plan

## Architecture: Pragmatic Modular Monolith

Each domain is a self-contained module under `module/`. Modules can be flat (simple CRUD) or nested (complex domains with sub-modules). Modules communicate via Service interfaces (not direct mapper calls), enabling future extraction to microservices.

---

## Phase 1: Foundation (core/)

### 1.1 — Project Configuration
- `application.properties`: H2, MyBatis, JWT config, API key config
- `application-h2.properties`: H2 console, datasource, SP mode
- `schema-h2.sql`: Tables + stored procedures
- `data-h2.sql`: Seed admin/admin user (BCrypt encoded)

**Suggested Skills:** `java-pro`, `database-design`

### 1.2 — API Response Framework
- `core/api/ApiResponse.java` — Generic wrapper `{code, message, data, timestamp}`
- `core/api/ApiCode.java` — Enum: SUCCESS, CREATED, BAD_REQUEST, UNAUTHORIZED, FORBIDDEN, NOT_FOUND, INTERNAL_ERROR
- `core/api/PageRequest.java` — Reusable pagination input (page, size, sort)

**Suggested Skills:** `api-patterns`, `api-design-principles`

### 1.3 — Exception Handling
- `core/exception/ErrorCode.java` — Enum grouped by module (AUTH_xxx, USER_xxx, COURSE_xxx)
- `core/exception/BusinessException.java` — extends RuntimeException, carries ErrorCode
- `core/exception/GlobalExceptionHandler.java` — @RestControllerAdvice, maps to ApiResponse

**Suggested Skills:** `error-handling-patterns`

### 1.4 — Security Foundation
- `core/security/JwtProvider.java` — Create/validate JWT, extract claims (usrNo, role)
- `core/security/JwtAuthFilter.java` — OncePerRequestFilter, reads Bearer token
- `core/security/ApiKeyAuthFilter.java` — Reads X-API-KEY header, validates against config
- `core/security/UserPrincipal.java` — Implements UserDetails, holds usrNo + role
- `core/security/SecurityUtil.java` — Static helper: getCurrentUsrNo(), getCurrentRole()
- `core/config/SecurityConfig.java` — Filter chain, permit/auth paths, CORS

**Suggested Skills:** `security-audit`, `api-security-best-practices`, `auth-implementation-patterns`

### 1.5 — MyBatis Configuration
- `core/config/MyBatisConfig.java` — Mapper scan, type aliases, type handlers
- Mapper XML location: `resources/mapper/{module}/*.xml`

**Suggested Skills:** `database`, `sql-pro`

---

## Phase 2: Auth Module (module/auth/)

### 2.1 — Entities & Mapper
- `RefreshToken.java` — Entity (tokenId, usrNo, token, expiresAt, createdAt)
- `RefreshTokenMapper.java` — MyBatis interface (SP calls)
- `mapper/RefreshTokenMapper.xml` — SP calls: sp_create_refresh_token, sp_find_by_token, sp_delete_by_usr_no, sp_delete_by_token

### 2.2 — Auth Strategy
- `AuthStrategy.java` — Interface: authenticate(LoginRequest), supports(String loginType)
- `UsernameAuthStrategy.java` — Validates username (email/phone/username) + password via BCrypt
- Future: `KakaoAuthStrategy.java`, `AppleAuthStrategy.java`

### 2.3 — Auth Service & Controller
- `AuthService.java` — login (delegates to strategy), refresh (token rotation), logout (revoke)
- `AuthController.java`:
  - `POST /api/v1/auth/login` — public
  - `POST /api/v1/auth/refresh` — public
  - `POST /api/v1/auth/logout` — JWT required
- `dto/LoginRequest.java` — { loginType, identifier, password }
- `dto/TokenResponse.java` — { accessToken, refreshToken, expiresIn, usrNo }

### 2.4 — Stored Procedures (schema-h2.sql)
```sql
sp_auth_create_refresh_token(p_usr_no, p_token, p_expires_at)
sp_auth_find_refresh_token_by_token(p_token)
sp_auth_delete_refresh_token_by_token(p_token)
sp_auth_delete_refresh_tokens_by_usr_no(p_usr_no)
```

**Suggested Skills:** `auth-implementation-patterns`, `api-security-best-practices`, `security-audit`

---

## Phase 3: User Module (module/user/)

### 3.1 — Entity & Enums
- `User.java` — (usrNo, username, password, nickname, role, status, createdAt, updatedAt)
- `UserRole.java` — ADMIN, USER
- `UserStatus.java` — ACTIVE, INACTIVE, BANNED

### 3.2 — Mapper (SP approach)
- `UserMapper.java` — MyBatis interface
- `mapper/UserMapper.xml` — SP calls:
```sql
sp_user_create(p_username, p_password, p_nickname, p_role, p_status)  → returns usr_no
sp_user_find_by_usr_no(p_usr_no)                                      → returns User
sp_user_find_by_username(p_username)                                  → returns User
sp_user_update(p_usr_no, p_nickname)                                  → returns affected rows
sp_user_delete(p_usr_no)                                              → soft delete (status=INACTIVE)
sp_user_list(p_page, p_size, p_role, p_status)                        → returns List<User> + total
```

### 3.3 — Service
- `UserService.java`:
  - createUser(UserRequest) → UserResponse
  - getUserByUsrNo(Long) → UserResponse
  - updateUser(Long, UserRequest) → UserResponse
  - deleteUser(Long) → void (soft delete)
  - listUsers(PageRequest, role, status) → PageResponse<UserResponse>

### 3.4 — Controller
- `UserController.java`:
  - `POST   /api/v1/users`           — register (public)
  - `GET    /api/v1/users/me`        — current user (JWT)
  - `GET    /api/v1/users/{usrNo}`   — get by usrNo (JWT)
  - `PUT    /api/v1/users/{usrNo}`   — update nickname (JWT, owner or admin)
  - `DELETE /api/v1/users/{usrNo}`   — soft delete (JWT, admin)
  - `GET    /api/v1/users`           — list (JWT, admin)

### 3.5 — DTOs (minimal)
- `dto/UserRequest.java` — { username, password, nickname } (validation groups for create vs update)
- `dto/UserResponse.java` — { usrNo, username, nickname, role, status, createdAt } (reused everywhere)

### 3.6 — Stored Procedures (schema-h2.sql)
All user operations as H2 aliases.

**Suggested Skills:** `api-patterns`, `sql-pro`, `clean-code`

---

## Phase 4: Course Module (module/course/) — Validates Architecture

### 4.1 — Entities
- `Course.java` — (courseNo, name, country, region, difficulty, distance, holeCount, imageUrl, status, playCount, createdAt)
- `CourseHole.java` — (holeNo, courseNo, holeNumber, par, hcp, distance, overviewImageUrl, greenImageUrl)

### 4.2 — Mapper (SP approach)
```sql
sp_search_courses(name, country, difficulty, distanceMin, distanceMax, sortBy, page, size)
sp_find_course_by_no(course_no)
sp_find_course_holes(course_no)
sp_get_popular_courses(limit)
sp_get_new_courses(limit)
sp_get_most_played_courses(limit)
```

### 4.3 — Service
- `CourseService.java`:
  - searchCourses(CourseSearchRequest) → PageResponse<CourseListResponse>
  - getCourseDetail(Long) → CourseDetailResponse (includes holes)
  - getPopularCourses(int limit) → List<CourseListResponse>
  - getNewCourses(int limit) → List<CourseListResponse>
  - getMostPlayedCourses(int limit) → List<CourseListResponse>

### 4.4 — Controller
- `CourseController.java`:
  - `GET /api/v1/courses`              — search with filters (JWT)
  - `GET /api/v1/courses/{courseNo}`    — course detail + holes (JWT)
  - `GET /api/v1/courses/popular`      — quick filter (JWT)
  - `GET /api/v1/courses/new`          — quick filter (JWT)
  - `GET /api/v1/courses/most-played`  — quick filter (JWT)

### 4.5 — DTOs
- `dto/CourseSearchRequest.java` — { name, country, difficulty, distanceMin, distanceMax, sortBy, page, size }
- `dto/CourseListResponse.java` — { courseNo, name, country, difficulty, distance, holeCount, imageUrl, playCount }
- `dto/CourseDetailResponse.java` — { ...all fields, List<CourseHoleResponse> holes }
- `dto/CourseHoleResponse.java` — { holeNumber, par, hcp, distance, overviewImageUrl, greenImageUrl }

**Suggested Skills:** `api-patterns`, `sql-pro`, `database-design`

---

## Phase 5: API Documentation & Testing

### 5.1 — SpringDoc OpenAPI
- Swagger UI at `/swagger-ui.html`
- Group APIs by module using @Tag
- Auth: Bearer token input in Swagger

### 5.2 — Testing
- Controller integration tests with MockMvc
- Service unit tests
- SP call tests with H2

**Suggested Skills:** `api-documentation`, `testing-patterns`

---

## Implementation Order (Dependencies)

```
Phase 1.1 (config)
    → Phase 1.2 (api response)
    → Phase 1.3 (exceptions)
    → Phase 1.5 (mybatis config)
    → Phase 1.4 (security)
        → Phase 2 (auth module)
            → Phase 3 (user module)
                → Phase 4 (course module)
                    → Phase 5 (docs + tests)
```

---

## Future Modules (not in scope, but architecture supports)

| Module | When | Notes |
|--------|------|-------|
| `module/event/tournament/` | Phase 2 | Sub-module under event domain |
| `module/event/league/` | Phase 2 | Sub-module under event domain |
| `module/ranking/` | Phase 3 | Leaderboard, HCP tracking |
| `module/store/` | Phase 3 | Item shop |
| `module/play-history/` | Phase 2-3 | Round records, scoring |
| `module/notification/` | Phase 3 | Push/in-app notifications (Kafka) |

---

## Decision Log

| # | Decision | Alternatives | Why |
|---|----------|-------------|-----|
| 1 | Pragmatic Modular Monolith | Full Hexagonal, Layered | Extractable modules without DTO explosion |
| 2 | SP approach (stored procedures via MyBatis) | Hybrid SP+XML, pure XML | User preference |
| 3 | JWT stateless auth | Opaque tokens, session-based | Shared token across services |
| 4 | Strategy pattern for auth | Single auth, if-else | Future SNS login without modifying code |
| 5 | Minimal DTOs (one per data shape) | DTO-per-operation | Less boilerplate, validation groups |
| 6 | Flat → sub-module → graduation | Fixed depth | Matches growth naturally |
| 7 | x-api-key from config (Phase 1) | DB keys | Simple start |
| 8 | H2 with SP syntax | PostgreSQL dev | Lower barrier, user-requested |
| 9 | Cross-module via Service interface | Direct mapper, events | Swappable to REST on extraction |
| 10 | URL versioning /api/v1/ | Header versioning | Easier to test and debug |
