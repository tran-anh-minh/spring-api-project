# Feed Feature — Design Document

## 1. Overview

A social feed feature (like Facebook feed) for Golfzon's golf simulator app. Users can share game scorecards, GDR sessions, video swings, swing analysis, images, videos, and text posts. Other users can comment, reply, and like. Feed supports moderation (hide by admin/store owner) and graceful degradation when either server is in maintenance.

---

## 2. System Architecture

### 2.1 — Service & Database Map

| Service | Databases Connected | Role |
|---------|-------------------|------|
| **GlobalAPI (= gsapi)** | Game DB, Video Swing Game DB, Swing Analysis DB | Game server + feed owner (primary feed store) |
| **gdrapi** | GDR DB, Video Swing GDR DB | Driving range server + GDR feed fallback |

### 2.2 — Feed Data Ownership

- **Game DB** is the **primary feed store** — all feed rows live here
- **GDR DB** holds a **read-only copy** (`feed_gdr` table) of GDR-type feed posts for fallback
- Comments and likes live in **Game DB only**
- Swing Analysis data lives in Game DB (covers both game and GDR analysis)

### 2.3 — Module Structure (GlobalAPI)

```
module/feed/
├── FeedController.java
├── FeedService.java
├── FeedCommandService.java         # create, update, delete, hide (split when >300 lines)
├── FeedQueryService.java           # list, detail, search
├── Feed.java                       # Entity
├── FeedMedia.java                  # Entity
├── FeedView.java                   # Entity
├── FeedType.java                   # Enum
├── FeedStatus.java                 # Enum
├── FeedVisibility.java             # Enum
├── FeedMapper.java
├── FeedMediaMapper.java
├── FeedViewMapper.java
├── dto/
│   ├── FeedRequest.java            # create/update input
│   ├── FeedSearchRequest.java      # list filters
│   ├── FeedListResponse.java       # card data (self-contained)
│   ├── FeedDetailResponse.java     # full detail
│   └── FeedSyncRequest.java        # internal API: dual write payload
├── client/
│   └── GdrApiClient.java           # server-to-server calls to gdrapi (x-api-key)
└── mapper/
    ├── FeedMapper.xml
    ├── FeedMediaMapper.xml
    └── FeedViewMapper.xml

module/comment/                      # Generic — shared by feed, event, tournament, etc.
├── CommentController.java
├── CommentService.java
├── Comment.java
├── CommentMapper.java
├── dto/
│   ├── CommentRequest.java
│   └── CommentResponse.java
└── mapper/
    └── CommentMapper.xml

module/like/                         # Generic — shared by feed, event, comment, etc.
├── LikeController.java
├── LikeService.java
├── LikeRecord.java
├── LikeMapper.java
├── dto/
│   └── LikeResponse.java
└── mapper/
    └── LikeMapper.xml
```

---

## 3. Database Schema

### 3.1 — Game DB Tables

```sql
-- ============================================
-- TABLE: feed (Primary store - Game DB)
-- ============================================
CREATE TABLE feed (
    feed_no         BIGINT          IDENTITY(1,1) PRIMARY KEY,
    usr_no          BIGINT          NOT NULL,
    feed_type       VARCHAR(20)     NOT NULL,
    status          VARCHAR(20)     NOT NULL DEFAULT 'PENDING',
    visibility      VARCHAR(10)     NOT NULL DEFAULT 'PUBLIC',
    content         NVARCHAR(2000)  NULL,

    -- Linked references (one populated based on feed_type)
    game_no         BIGINT          NULL,
    video_id        BIGINT          NULL,
    gdr_no          BIGINT          NULL,
    gdr_video_id    BIGINT          NULL,
    analysis_id     BIGINT          NULL,

    -- Snapshot (self-contained card data)
    snapshot_data   NVARCHAR(MAX)   NULL,

    -- Location
    store_no        BIGINT          NULL,

    -- Denormalized filter fields
    country_cd      VARCHAR(10)     NULL,
    sex_cd          VARCHAR(1)      NULL,

    -- Counters (denormalized, updated by SP)
    like_cnt        INT             NOT NULL DEFAULT 0,
    comment_cnt     INT             NOT NULL DEFAULT 0,
    share_cnt       INT             NOT NULL DEFAULT 0,
    view_cnt        INT             NOT NULL DEFAULT 0,

    -- Moderation
    is_hidden       BIT             NOT NULL DEFAULT 0,
    hidden_by       BIGINT          NULL,
    hidden_reason   NVARCHAR(500)   NULL,
    hidden_at       DATETIME2       NULL,

    -- Audit
    created_at      DATETIME2       NOT NULL DEFAULT SYSDATETIME(),
    updated_at      DATETIME2       NOT NULL DEFAULT SYSDATETIME(),
    del_yn          CHAR(1)         NOT NULL DEFAULT 'N',

    CONSTRAINT chk_feed_type CHECK (feed_type IN ('GAME','GDR','SWING_GAME','SWING_GDR','ANALYSIS','IMAGE','VIDEO','TEXT')),
    CONSTRAINT chk_feed_status CHECK (status IN ('PENDING','ACTIVE','FAILED')),
    CONSTRAINT chk_feed_visibility CHECK (visibility IN ('PUBLIC','STORE')),
    CONSTRAINT chk_feed_del CHECK (del_yn IN ('Y','N'))
);

CREATE INDEX ix_feed_list_default   ON feed (created_at DESC) WHERE del_yn = 'N' AND is_hidden = 0;
CREATE INDEX ix_feed_store          ON feed (store_no, created_at DESC) WHERE del_yn = 'N' AND is_hidden = 0;
CREATE INDEX ix_feed_type           ON feed (feed_type, created_at DESC) WHERE del_yn = 'N' AND is_hidden = 0;
CREATE INDEX ix_feed_country        ON feed (country_cd, created_at DESC) WHERE del_yn = 'N' AND is_hidden = 0;
CREATE INDEX ix_feed_usr            ON feed (usr_no, created_at DESC) WHERE del_yn = 'N';

-- ============================================
-- TABLE: feed_media
-- ============================================
CREATE TABLE feed_media (
    media_no        BIGINT          IDENTITY(1,1) PRIMARY KEY,
    feed_no         BIGINT          NOT NULL,
    media_type      VARCHAR(10)     NOT NULL,
    media_url       NVARCHAR(500)   NOT NULL,
    thumbnail_url   NVARCHAR(500)   NULL,
    sort_order      INT             NOT NULL DEFAULT 0,
    created_at      DATETIME2       NOT NULL DEFAULT SYSDATETIME(),

    CONSTRAINT chk_media_type CHECK (media_type IN ('IMAGE','VIDEO'))
);

CREATE INDEX ix_media_feed ON feed_media (feed_no, sort_order);

-- ============================================
-- TABLE: feed_view
-- ============================================
CREATE TABLE feed_view (
    view_no         BIGINT          IDENTITY(1,1) PRIMARY KEY,
    feed_no         BIGINT          NOT NULL,
    usr_no          BIGINT          NULL,
    created_at      DATETIME2       NOT NULL DEFAULT SYSDATETIME()
);

CREATE INDEX ix_view_feed ON feed_view (feed_no);

-- ============================================
-- TABLE: comment (generic - module/comment/)
-- ============================================
CREATE TABLE comment (
    comment_no          BIGINT          IDENTITY(1,1) PRIMARY KEY,
    target_type         VARCHAR(20)     NOT NULL,
    target_no           BIGINT          NOT NULL,
    usr_no              BIGINT          NOT NULL,
    parent_comment_no   BIGINT          NULL,
    mention_usr_no      BIGINT          NULL,
    mention_nickname    NVARCHAR(50)    NULL,
    content             NVARCHAR(1000)  NOT NULL,

    is_hidden           BIT             NOT NULL DEFAULT 0,
    hidden_by           BIGINT          NULL,
    hidden_at           DATETIME2       NULL,

    created_at          DATETIME2       NOT NULL DEFAULT SYSDATETIME(),
    updated_at          DATETIME2       NOT NULL DEFAULT SYSDATETIME(),
    del_yn              CHAR(1)         NOT NULL DEFAULT 'N',

    CONSTRAINT chk_comment_target CHECK (target_type IN ('FEED','EVENT','TOURNAMENT')),
    CONSTRAINT chk_comment_del CHECK (del_yn IN ('Y','N'))
);

CREATE INDEX ix_comment_target  ON comment (target_type, target_no, created_at ASC) WHERE del_yn = 'N';
CREATE INDEX ix_comment_parent  ON comment (parent_comment_no) WHERE del_yn = 'N';
CREATE INDEX ix_comment_usr     ON comment (usr_no) WHERE del_yn = 'N';

-- ============================================
-- TABLE: like_record (generic - module/like/)
-- ============================================
CREATE TABLE like_record (
    like_no         BIGINT          IDENTITY(1,1) PRIMARY KEY,
    target_type     VARCHAR(20)     NOT NULL,
    target_no       BIGINT          NOT NULL,
    usr_no          BIGINT          NOT NULL,
    created_at      DATETIME2       NOT NULL DEFAULT SYSDATETIME(),

    CONSTRAINT uq_like UNIQUE (target_type, target_no, usr_no),
    CONSTRAINT chk_like_target CHECK (target_type IN ('FEED','EVENT','COMMENT','TOURNAMENT'))
);
```

### 3.2 — GDR DB Table (Fallback Copy)

```sql
-- ============================================
-- GDR DB: feed_gdr (read-only copy for fallback)
-- ============================================
CREATE TABLE feed_gdr (
    feed_no         BIGINT          PRIMARY KEY,        -- NOT identity, copied from Game DB
    usr_no          BIGINT          NOT NULL,
    feed_type       VARCHAR(20)     NOT NULL,
    visibility      VARCHAR(10)     NOT NULL DEFAULT 'PUBLIC',
    content         NVARCHAR(2000)  NULL,

    gdr_no          BIGINT          NULL,
    gdr_video_id    BIGINT          NULL,

    snapshot_data   NVARCHAR(MAX)   NULL,

    store_no        BIGINT          NULL,
    country_cd      VARCHAR(10)     NULL,
    sex_cd          VARCHAR(1)      NULL,

    like_cnt        INT             NOT NULL DEFAULT 0,
    comment_cnt     INT             NOT NULL DEFAULT 0,
    share_cnt       INT             NOT NULL DEFAULT 0,
    view_cnt        INT             NOT NULL DEFAULT 0,

    is_hidden       BIT             NOT NULL DEFAULT 0,

    created_at      DATETIME2       NOT NULL,
    updated_at      DATETIME2       NOT NULL,
    del_yn          CHAR(1)         NOT NULL DEFAULT 'N'
);

CREATE INDEX ix_feed_gdr_list   ON feed_gdr (created_at DESC) WHERE del_yn = 'N' AND is_hidden = 0;
CREATE INDEX ix_feed_gdr_store  ON feed_gdr (store_no, created_at DESC) WHERE del_yn = 'N' AND is_hidden = 0;
```

---

## 4. Data Flows

### 4.1 — Create Feed (Async)

```
Webapp → POST /api/v1/feeds → GlobalAPI
  1. [SYNC] Validate input → insert feed with status=PENDING → return ACCEPTED
  2. [ASYNC thread]
     a. Fetch snapshot:
        - GAME/SWING_GAME/ANALYSIS → query own DB
        - GDR/SWING_GDR → GET /internal/gdr-sessions/{gdrNo} from gdrapi (x-api-key)
        - IMAGE/VIDEO/TEXT → no external call
     b. Upload media (if any) → store URLs
     c. Write snapshot + media to Game DB
     d. Update feed status → ACTIVE
     e. If GDR type → dual write to gdrapi: POST /internal/feeds/sync (x-api-key)
     f. Send notification (if applicable)
     g. On failure → update status → FAILED
```

### 4.2 — Feed List

```
Webapp → GET /api/v1/feeds?storeNo=&feedType=&sexCd=&countryCd=&page=&size= → GlobalAPI
  1. sp_feed_search with filters
     - Excludes: is_hidden=1, del_yn='Y', status != ACTIVE (except own PENDING/FAILED)
     - Handles visibility: PUBLIC shown to all, STORE shown only to same-store users
  2. Returns self-contained cards: snapshot_data, media[], counters, isLiked
```

### 4.3 — Feed Detail

```
Webapp determines API by feedType:
  - GAME, SWING_GAME, ANALYSIS, IMAGE/VIDEO/TEXT → GlobalAPI GET /api/v1/feeds/{feedNo}
  - GDR, SWING_GDR → gdrapi GET /api/v1/feeds/{feedNo}

GlobalAPI detail:
  1. sp_feed_detail → feed + media
  2. Increment view_cnt (Game DB only)
  3. If GDR type → sync updated counters to gdrapi
  4. Load comments (from comment module)
  5. Return FeedDetailResponse

gdrapi detail (fallback when GlobalAPI down):
  1. Read from feed_gdr + own GDR DB for session detail
  2. No view_cnt increment
  3. No comments (disabled)
  4. Return FeedDetailResponse
```

### 4.4 — Like Toggle

```
Webapp → POST /api/v1/likes {targetType: FEED, targetNo: feedNo} → GlobalAPI
  1. sp_like_toggle (insert or delete in like_record)
  2. sp_feed_update_like_cnt
  3. If GDR feed → sync counters to gdrapi
  4. Return {liked: true/false, likeCnt: N}
```

### 4.5 — Comment / Reply

```
Webapp → POST /api/v1/comments {targetType: FEED, targetNo: feedNo, content, parentCommentNo?, mentionUsrNo?} → GlobalAPI
  1. Validate feed exists & not hidden
  2. If reply → validate parent exists & is top-level & same target
  3. Resolve mention_nickname from mentionUsrNo
  4. sp_comment_create
  5. sp_feed_update_comment_cnt
  6. If GDR feed → sync counters to gdrapi
  7. Send notification to feed author (and mentioned user if reply)
  8. Return CommentResponse
```

### 4.6 — Moderation (Hide)

```
Webapp → PUT /api/v1/feeds/{feedNo}/hide {reason} → GlobalAPI
  1. Check role: ADMIN → any feed, STORE_OWNER → own store feeds only
  2. sp_feed_hide (set is_hidden, hidden_by, hidden_reason, hidden_at)
  3. If GDR feed → sync is_hidden to gdrapi
```

### 4.7 — User Account Removal (Cascade)

```
User account removal triggers (within transaction or SP chain):
  1. sp_feed_hide_by_usr(usr_no) → hide all their feed posts
  2. sp_comment_hide_by_usr(usr_no) → hide all their comments + replies to their comments
  3. Update comment_cnt on all affected feeds
  4. For affected GDR feeds → sync is_hidden + counters to gdrapi
```

### 4.8 — GDR Fallback (GlobalAPI Down)

```
Webapp detects GlobalAPI unreachable → switches to gdrapi

Available (read-only):
  - GET /api/v1/feeds → GDR/SWING_GDR feed list from feed_gdr
  - GET /api/v1/feeds/{feedNo} → GDR feed detail from feed_gdr + GDR DB

Disabled:
  - Create feed
  - Comments / replies
  - Like toggle
  - View count increment
  - Moderation actions
  - Share count increment
```

---

## 5. Dual Write Sync Points

Every write to a GDR-type feed triggers a sync call to gdrapi:

| Action | What is synced to feed_gdr |
|--------|--------------------------|
| Feed create (GDR type) | Full feed_gdr row |
| Feed update | content, snapshot_data, updated_at |
| Feed delete | del_yn = 'Y' |
| Feed hide/unhide | is_hidden |
| Like toggle | like_cnt |
| Comment create/delete | comment_cnt |
| Share button tap | share_cnt |
| View detail | view_cnt |
| User account removal | is_hidden on affected feeds, comment_cnt |

Internal API endpoint on gdrapi: `POST /internal/feeds/sync` with x-api-key auth.

---

## 6. Stored Procedures

### Feed Module (Game DB)
| SP Name | Purpose |
|---------|---------|
| sp_feed_create | Insert feed row, return feed_no |
| sp_feed_update | Update content, snapshot, status |
| sp_feed_update_status | Update status (PENDING→ACTIVE/FAILED) |
| sp_feed_delete | Soft delete (del_yn = 'Y') |
| sp_feed_hide | Set is_hidden, hidden_by, reason, hidden_at |
| sp_feed_unhide | Reverse hide |
| sp_feed_hide_by_usr | Hide all feeds by usr_no (account removal) |
| sp_feed_find_by_feed_no | Get single feed with user info |
| sp_feed_search | Paginated search with all filters |
| sp_feed_update_like_cnt | Increment/decrement like_cnt |
| sp_feed_update_comment_cnt | Increment/decrement comment_cnt |
| sp_feed_update_share_cnt | Increment share_cnt |
| sp_feed_update_view_cnt | Increment view_cnt |
| sp_feed_media_create | Insert media row |
| sp_feed_media_find_by_feed_no | Get all media for a feed |
| sp_feed_media_delete_by_feed_no | Remove media on feed edit |
| sp_feed_view_create | Insert view record + increment view_cnt |

### Comment Module (Game DB)
| SP Name | Purpose |
|---------|---------|
| sp_comment_create | Insert comment/reply |
| sp_comment_find_by_target | Get comments tree for a target |
| sp_comment_count_by_target | Comment count |
| sp_comment_delete | Soft delete |
| sp_comment_hide | Hide comment (admin/owner) |
| sp_comment_hide_by_usr | Hide all by usr_no + their replies (account removal) |

### Like Module (Game DB)
| SP Name | Purpose |
|---------|---------|
| sp_like_toggle | Insert or delete like |
| sp_like_count | Count by target |
| sp_like_check | Check if user liked target |

### GDR DB (gdrapi)
| SP Name | Purpose |
|---------|---------|
| sp_feed_gdr_upsert | Insert or update feed_gdr row (sync from GlobalAPI) |
| sp_feed_gdr_search | Paginated search (fallback feed list) |
| sp_feed_gdr_find_by_feed_no | Single feed detail (fallback) |
| sp_feed_gdr_update_counters | Update counter fields |
| sp_feed_gdr_update_hidden | Update is_hidden flag |
| sp_feed_gdr_delete | Soft delete |

---

## 7. API Endpoints

### Feed (GlobalAPI)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | /api/v1/feeds | JWT | Create feed (returns ACCEPTED, async processing) |
| GET | /api/v1/feeds | JWT | List feed with filters |
| GET | /api/v1/feeds/{feedNo} | JWT | Feed detail + comments |
| PUT | /api/v1/feeds/{feedNo} | JWT | Update own feed |
| DELETE | /api/v1/feeds/{feedNo} | JWT | Delete own feed |
| PUT | /api/v1/feeds/{feedNo}/hide | JWT (ADMIN/STORE_OWNER) | Hide feed |
| PUT | /api/v1/feeds/{feedNo}/unhide | JWT (ADMIN/STORE_OWNER) | Unhide feed |
| POST | /api/v1/feeds/{feedNo}/share | JWT | Increment share count |

### Comment (GlobalAPI)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | /api/v1/comments | JWT | Create comment/reply |
| GET | /api/v1/comments?targetType=&targetNo= | JWT | List comments for target |
| DELETE | /api/v1/comments/{commentNo} | JWT | Delete own comment |
| PUT | /api/v1/comments/{commentNo}/hide | JWT (ADMIN/STORE_OWNER) | Hide comment |

### Like (GlobalAPI)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | /api/v1/likes | JWT | Toggle like |
| GET | /api/v1/likes/check?targetType=&targetNo= | JWT | Check if liked |

### Internal (gdrapi — x-api-key only)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| POST | /internal/feeds/sync | x-api-key | Upsert feed_gdr row |
| POST | /internal/feeds/{feedNo}/counters | x-api-key | Sync counters |
| POST | /internal/feeds/{feedNo}/hidden | x-api-key | Sync is_hidden |
| POST | /internal/feeds/{feedNo}/delete | x-api-key | Sync soft delete |
| GET | /internal/gdr-sessions/{gdrNo} | x-api-key | Fetch GDR snapshot for feed creation |

### Fallback (gdrapi — when GlobalAPI is down)
| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| GET | /api/v1/feeds | JWT | GDR feed list (read-only) |
| GET | /api/v1/feeds/{feedNo} | JWT | GDR feed detail (no comments) |

---

## 8. Maintenance Mode Behavior

| Scenario | Feed List | Detail | Create | Comments/Likes | Moderation |
|----------|-----------|--------|--------|---------------|------------|
| Both up | All feed from GlobalAPI | Game→GlobalAPI, GDR→gdrapi | All types | Enabled | Enabled |
| GlobalAPI down | GDR feed only from gdrapi | GDR→gdrapi only | Disabled | Disabled | Disabled |
| gdrapi down | Game + IMAGE/VIDEO/TEXT from GlobalAPI | Game→GlobalAPI only | Game types + IMAGE/VIDEO/TEXT only | Enabled | Enabled (game feeds) |

---

## 9. Decision Log

| # | Decision | Alternatives Considered | Why |
|---|----------|------------------------|-----|
| 1 | Feed primary store in Game DB | Separate feed DB, centralized DB | GlobalAPI IS gsapi — no new DB needed, simplest topology |
| 2 | Dual write GDR feed to GDR DB | Kafka async, DB replication, scheduled sync | Immediate consistency, simple, user confirmed |
| 3 | Server-to-server snapshot via internal API (x-api-key) | Client-sends snapshot, reference-only lazy fetch | Trusted data (not client-submitted), self-contained feed cards, matches existing x-api-key pattern |
| 4 | Async feed creation (PENDING→ACTIVE/FAILED) | Synchronous creation | Responsive UX, decouples snapshot fetching from user request |
| 5 | Snapshot as JSON (NVARCHAR MAX) | Normalized snapshot columns, separate snapshot table | Flexible per feed type, no schema change when game/GDR data shape evolves |
| 6 | Denormalized counters on feed table | COUNT queries on like/comment/view tables | Performance at millions of users — avoids COUNT on every feed list query |
| 7 | Denormalized country_cd and sex_cd on feed | JOIN to user/store tables | Fast filter queries without joins |
| 8 | Generic comment module (target_type + target_no) | Feed-specific comment table | Reusable for event, tournament, etc. per user request |
| 9 | Generic like module (target_type + target_no) | Feed-specific like table | Reusable for event, comment, tournament, etc. |
| 10 | Comments/likes in Game DB only, disabled when GlobalAPI down | Dual write comments too | Simplicity — comments are less critical than feed visibility during maintenance |
| 11 | All counter writes in Game DB only, synced to feed_gdr | Independent counter tracking in GDR DB | Single source of truth, no reconciliation needed |
| 12 | GDR feed creation rejected when gdrapi is down | Queue and retry, accept with partial data | Can't fetch snapshot — clean failure, user retries when gdrapi is back |
| 13 | Visibility: PUBLIC or STORE (author chooses per post) | Always public, always store-scoped | User requested per-post choice |
| 14 | User account removal cascades: hide feeds + hide comments + hide replies | Hard delete, keep visible | Soft hide preserves data integrity, notification strings accepted as non-reversible |
| 15 | Feed module as single module with Command/Query service split | Separate feed + feed-comment modules, event-driven | Follows conventions (flat module, split when >300 lines), comment is now a separate generic module |
