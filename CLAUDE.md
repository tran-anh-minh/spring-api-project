# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Required Reading

Before implementing or reviewing any feature, read these documents:
- **`.claude/plan/CONVENTIONS.md`** — Layer rules, DTO strategy, logging, error handling, SP conventions, transactions, date/time, pagination, **code review checklist (Section 15)**
- **`.claude/plan/IMPLEMENTATION_PLAN.md`** — Phase plan, decision log, module structure

## Custom Skills

- **`/best-prompt`** — Refines vague requests into clear, precise prompts with convention injection before execution.
- **`/review-code`** — Validates code against CONVENTIONS.md Section 15. Run after writing code or before committing.
- **`/update-convention`** — Evolves CONVENTIONS.md when a gap is found. Proposes changes with examples, user confirms.
- **`/brainstorming`** — Structured design session for new features/architecture before implementation.

### Convention Enforcement Workflow

```
/best-prompt  →  (write code)  →  /review-code  →  /update-convention (if gap found)
 [PREVENT]                         [VERIFY]          [EVOLVE]
```

## Project Overview

GlobalAPI is a Spring Boot 4.0.3 REST API (Java 17) for a simulator golf app by Golfzon. Maven build system.

## Build & Development Commands

```bash
./mvnw clean package -DskipTests    # Build (skip tests)
./mvnw test                          # Run all tests
./mvnw test -Dtest=ClassName         # Run single test class
./mvnw test -Dtest=Class#method      # Run single test method
./mvnw spring-boot:run               # Run the application
```

## Architecture: Pragmatic Modular Monolith

- **Base package:** `com.golfzon.globalapi`
- **Pattern:** Modular monolith — each domain is a self-contained module under `module/`
- **Data access:** MyBatis stored procedures only (NO JPA, NO inline SQL)
- **Auth:** JWT (stateless) + x-api-key for internal services
- **API format:** Wrapped response `{code, message, data, timestamp}`, URL versioning `/api/v1/`

### Package Structure

```
core/                          → Shared foundation (security, config, exceptions, API response)
module/                        → Feature modules — each is self-contained:
  module/{name}/               →   Controller, Service, Entity, Enums, Mapper, dto/, mapper/
  module/{name}/{sub}/         →   Sub-modules for complex domains (e.g., event/tournament/)
resources/mapper/{module}/     → MyBatis XML files (SP calls only)
```

### Key Rules

- **Flat module structure** — each module contains its own controller, service, entity, mapper, DTOs together
- **Entities are pure** — no Spring, no MyBatis annotations, no `@Data` (use `@Getter`/`@Setter`)
- **Services call other modules via Service interfaces**, never via mappers directly
- **All DB access through stored procedures** — naming: `sp_{module}_{action}`
- **Minimal DTOs** — one per data shape, not per endpoint. Use validation groups for create vs update
- **Controllers are thin** — validate, delegate to service, return `ApiResponse<T>`
- **Never expose domain entities in API responses** — always map to Response DTOs
- **Logging:** `@Slf4j`, structured key-value format, module prefix `[AUTH]`, `[USER]`, etc.
- **Errors:** Throw `BusinessException(ErrorCode.XXX)` in services, `GlobalExceptionHandler` converts to `ApiResponse`

### Module Scaling

Flat module → Sub-modules (when 3+ aggregate roots) → Graduate to top-level → Extract to microservice

## Stack

MyBatis (SP-only) | Spring Security (JWT + API Key) | Redis (cache) | Kafka (messaging) | Elasticsearch (search) | SpringDoc OpenAPI | Lombok | H2 (dev)
