-- Disalin apa adanya dari docs/spec/05-database.md §5 (v1.2), tanpa PRAGMA.
CREATE TABLE layout_presets (
  id          INTEGER PRIMARY KEY,
  code        TEXT NOT NULL CHECK (code IN ('gaming','podcast','irl','split_two','center_crop','custom')),
  name        TEXT NOT NULL UNIQUE,
  is_builtin  INTEGER NOT NULL DEFAULT 0 CHECK (is_builtin IN (0,1)),
  params      TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(params)),
  created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE channels (
  id                        INTEGER PRIMARY KEY,
  platform                  TEXT NOT NULL CHECK (platform IN ('youtube','kick','local')),
  external_id               TEXT,
  name                      TEXT NOT NULL CHECK (length(name) BETWEEN 1 AND 200),
  default_layout_preset_id  INTEGER REFERENCES layout_presets(id) ON DELETE SET NULL,
  created_at                TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  updated_at                TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  UNIQUE (platform, external_id)
);
CREATE INDEX ix_channels_default_preset ON channels(default_layout_preset_id);

CREATE TABLE source_streams (
  id                          INTEGER PRIMARY KEY,
  channel_id                  INTEGER REFERENCES channels(id) ON DELETE SET NULL,
  source_type                 TEXT NOT NULL CHECK (source_type IN ('vod_url','live_url','local_file')),
  platform                    TEXT NOT NULL CHECK (platform IN ('youtube','kick','local')),
  source_url                  TEXT,
  external_video_id           TEXT,
  title                       TEXT NOT NULL CHECK (length(title) BETWEEN 1 AND 500),
  duration_ms                 INTEGER CHECK (duration_ms >= 0),
  status                      TEXT NOT NULL DEFAULT 'queued'
                              CHECK (status IN ('queued','downloading','recording','processing','ready','failed')),
  detected_language           TEXT,
  has_chat                    INTEGER NOT NULL DEFAULT 0 CHECK (has_chat IN (0,1)),
  suggested_layout_preset_id  INTEGER REFERENCES layout_presets(id) ON DELETE SET NULL,
  video_path                  TEXT,
  video_width                 INTEGER CHECK (video_width > 0),
  video_height                INTEGER CHECK (video_height > 0),
  video_fps                   REAL CHECK (video_fps > 0),
  source_deleted_at           TEXT,
  live_analysis_enabled       INTEGER NOT NULL DEFAULT 0 CHECK (live_analysis_enabled IN (0,1)),
  live_started_at             TEXT,
  error_message               TEXT,
  created_at                  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  updated_at                  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  CHECK (source_type = 'local_file' OR source_url IS NOT NULL),
  CHECK ((source_type = 'local_file') = (platform = 'local'))
);
CREATE INDEX ix_streams_channel ON source_streams(channel_id);
CREATE INDEX ix_streams_status ON source_streams(status, created_at DESC);
CREATE INDEX ix_streams_suggested_preset ON source_streams(suggested_layout_preset_id);

CREATE TABLE subtitle_styles (
  id                  INTEGER PRIMARY KEY,
  name                TEXT NOT NULL UNIQUE CHECK (length(name) BETWEEN 1 AND 60),
  is_builtin          INTEGER NOT NULL DEFAULT 0 CHECK (is_builtin IN (0,1)),
  mode                TEXT NOT NULL CHECK (mode IN ('sentence','word_highlight')),
  font_family         TEXT NOT NULL DEFAULT 'Montserrat',
  font_size           INTEGER NOT NULL DEFAULT 64 CHECK (font_size BETWEEN 24 AND 160),
  primary_color       TEXT NOT NULL DEFAULT '#FFFFFF' CHECK (primary_color GLOB '#[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]'),
  highlight_color     TEXT NOT NULL DEFAULT '#FFD400' CHECK (highlight_color GLOB '#[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]'),
  outline_color       TEXT NOT NULL DEFAULT '#000000' CHECK (outline_color GLOB '#[0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f][0-9A-Fa-f]'),
  outline_width       INTEGER NOT NULL DEFAULT 4 CHECK (outline_width BETWEEN 0 AND 12),
  uppercase           INTEGER NOT NULL DEFAULT 0 CHECK (uppercase IN (0,1)),
  max_words_per_line  INTEGER NOT NULL DEFAULT 3 CHECK (max_words_per_line BETWEEN 1 AND 8),
  max_chars_per_line  INTEGER NOT NULL DEFAULT 42 CHECK (max_chars_per_line BETWEEN 10 AND 60),
  position_pct        INTEGER NOT NULL DEFAULT 70 CHECK (position_pct BETWEEN 5 AND 95),
  created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE live_markers (
  id                INTEGER PRIMARY KEY,
  source_stream_id  INTEGER NOT NULL REFERENCES source_streams(id) ON DELETE CASCADE,
  kind              TEXT NOT NULL CHECK (kind IN ('last_n_seconds','start_end')),
  start_ms          INTEGER NOT NULL CHECK (start_ms >= 0),
  end_ms            INTEGER CHECK (end_ms > start_ms),
  created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX ix_markers_stream ON live_markers(source_stream_id, start_ms);

CREATE TABLE clips (
  id                  INTEGER PRIMARY KEY,
  source_stream_id    INTEGER NOT NULL REFERENCES source_streams(id) ON DELETE CASCADE,
  origin              TEXT NOT NULL CHECK (origin IN ('auto','live_marker','manual')),
  live_marker_id      INTEGER UNIQUE REFERENCES live_markers(id) ON DELETE SET NULL,
  status              TEXT NOT NULL DEFAULT 'candidate'
                      CHECK (status IN ('candidate','approved','rejected','rendering','rendered','render_failed')),
  start_ms            INTEGER NOT NULL CHECK (start_ms >= 0),
  end_ms              INTEGER NOT NULL CHECK (end_ms > start_ms),
  score               INTEGER CHECK (score BETWEEN 0 AND 100),
  score_audio         REAL CHECK (score_audio BETWEEN 0 AND 1),
  score_chat          REAL CHECK (score_chat BETWEEN 0 AND 1),
  score_llm           INTEGER CHECK (score_llm BETWEEN 0 AND 100),
  score_partial       INTEGER NOT NULL DEFAULT 0 CHECK (score_partial IN (0,1)),
  category            TEXT CHECK (category IN ('lucu','hype','kontroversial','informatif','emosional','lainnya')),
  reason              TEXT CHECK (length(reason) <= 200),
  title               TEXT CHECK (length(title) <= 100),
  layout_preset_id    INTEGER NOT NULL REFERENCES layout_presets(id) ON DELETE RESTRICT,
  subtitle_style_id   INTEGER NOT NULL REFERENCES subtitle_styles(id) ON DELETE RESTRICT,
  subtitle_language   TEXT NOT NULL DEFAULT 'source' CHECK (subtitle_language IN ('source','id')),
  subtitle_overrides  TEXT CHECK (subtitle_overrides IS NULL OR json_valid(subtitle_overrides)),
  translated_lines    TEXT CHECK (translated_lines IS NULL OR json_valid(translated_lines)),
  caption_drafts      TEXT CHECK (caption_drafts IS NULL OR json_valid(caption_drafts)),
  output_video_path   TEXT,
  output_srt_path     TEXT,
  rendered_at         TEXT,
  render_error        TEXT,
  created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  -- BR-004: durasi 15–90 detik wajib untuk status setelah review
  CHECK (status IN ('candidate','rejected') OR (end_ms - start_ms) BETWEEN 15000 AND 90000),
  CHECK (origin = 'live_marker' OR live_marker_id IS NULL),
  CHECK (status <> 'rendered' OR output_video_path IS NOT NULL)
);
CREATE INDEX ix_clips_stream ON clips(source_stream_id, status, score DESC);
CREATE INDEX ix_clips_preset ON clips(layout_preset_id);
CREATE INDEX ix_clips_style ON clips(subtitle_style_id);

CREATE TABLE upload_accounts (
  id                   INTEGER PRIMARY KEY,
  platform             TEXT NOT NULL CHECK (platform IN ('youtube','tiktok','instagram','facebook')),
  external_account_id  TEXT NOT NULL,
  target_id            TEXT,
  display_name         TEXT NOT NULL,
  keyring_ref          TEXT NOT NULL UNIQUE,
  scopes               TEXT NOT NULL,
  account_status       TEXT NOT NULL DEFAULT 'connected' CHECK (account_status IN ('connected','needs_reauth','disconnected')),
  token_expires_at     TEXT,
  connected_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  last_error           TEXT,
  UNIQUE (platform, external_account_id),
  CHECK (platform NOT IN ('facebook','instagram') OR target_id IS NOT NULL)
);
CREATE UNIQUE INDEX ux_accounts_one_connected ON upload_accounts(platform)
  WHERE account_status = 'connected';

CREATE TABLE uploads (
  id                     INTEGER PRIMARY KEY,
  clip_id                INTEGER NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
  platform               TEXT NOT NULL CHECK (platform IN ('youtube','tiktok','instagram','facebook')),
  mode                   TEXT NOT NULL DEFAULT 'manual' CHECK (mode IN ('manual','auto')),
  upload_account_id      INTEGER REFERENCES upload_accounts(id) ON DELETE RESTRICT,
  status                 TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','uploading','uploaded','failed')),
  title                  TEXT CHECK (title IS NULL OR length(title) BETWEEN 1 AND 100),
  caption                TEXT NOT NULL DEFAULT '' CHECK (length(caption) <= 5000),
  hashtags               TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(hashtags)),
  visibility             TEXT CHECK (visibility IN ('private','unlisted','public','followers')),
  resumable_session_url  TEXT,
  platform_publish_id    TEXT,
  attempts               INTEGER NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 3),
  external_post_id       TEXT,
  external_url           TEXT,
  posted_as_private      INTEGER NOT NULL DEFAULT 0 CHECK (posted_as_private IN (0,1)),
  error_message          TEXT,
  uploaded_at            TEXT,
  created_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  updated_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  CHECK (mode = 'manual' OR upload_account_id IS NOT NULL),                 -- BR-013
  CHECK (mode = 'auto' OR status IN ('pending','uploaded')),                -- manual tidak punya uploading/failed
  CHECK (mode = 'auto' OR visibility IS NULL),
  CHECK (platform <> 'youtube' OR title IS NOT NULL),
  CHECK (mode = 'manual' OR status <> 'uploaded' OR external_post_id IS NOT NULL)
);
CREATE INDEX ix_uploads_clip ON uploads(clip_id);
CREATE INDEX ix_uploads_account ON uploads(upload_account_id);
CREATE INDEX ix_uploads_status_mode ON uploads(status, mode);
CREATE UNIQUE INDEX ux_uploads_active ON uploads(clip_id, platform)
  WHERE status IN ('pending','uploading','uploaded');           -- BR-009

CREATE TABLE jobs (
  id                     INTEGER PRIMARY KEY,
  job_type               TEXT NOT NULL CHECK (job_type IN ('download','record_live','transcribe','detect_layout','score_highlights','render','upload')),
  status                 TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed','cancelled')),
  source_stream_id       INTEGER REFERENCES source_streams(id) ON DELETE CASCADE,
  clip_id                INTEGER REFERENCES clips(id) ON DELETE CASCADE,
  upload_id              INTEGER REFERENCES uploads(id) ON DELETE CASCADE,
  purpose                TEXT NOT NULL DEFAULT 'final' CHECK (purpose IN ('final','preview')),
  preview_at_ms          INTEGER CHECK (preview_at_ms >= 0),
  scope_start_ms         INTEGER CHECK (scope_start_ms >= 0),
  scope_end_ms           INTEGER CHECK (scope_end_ms > scope_start_ms),
  is_heavy               INTEGER NOT NULL DEFAULT 1 CHECK (is_heavy IN (0,1)),
  priority               INTEGER NOT NULL DEFAULT 0,
  awaiting_confirmation  INTEGER NOT NULL DEFAULT 0 CHECK (awaiting_confirmation IN (0,1)),
  progress_pct           INTEGER NOT NULL DEFAULT 0 CHECK (progress_pct BETWEEN 0 AND 100),
  stage                  TEXT,
  checkpoint             TEXT CHECK (checkpoint IS NULL OR json_valid(checkpoint)),
  log_tail               TEXT CHECK (length(log_tail) <= 4000),
  error_message          TEXT,
  retry_of_job_id        INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
  worker_heartbeat_at    TEXT,
  started_at             TEXT,
  finished_at            TEXT,
  created_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  updated_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  CHECK (job_type = 'upload' OR source_stream_id IS NOT NULL),
  CHECK (job_type <> 'render' OR clip_id IS NOT NULL),
  CHECK (job_type <> 'upload' OR upload_id IS NOT NULL),
  CHECK ((scope_start_ms IS NULL) = (scope_end_ms IS NULL)),
  CHECK (purpose = 'final' OR (job_type = 'render' AND preview_at_ms IS NOT NULL))
);
CREATE INDEX ix_jobs_claim ON jobs(status, awaiting_confirmation, is_heavy, priority DESC, created_at);
CREATE INDEX ix_jobs_stream ON jobs(source_stream_id, created_at DESC);
CREATE INDEX ix_jobs_clip ON jobs(clip_id);
CREATE INDEX ix_jobs_upload ON jobs(upload_id);
CREATE INDEX ix_jobs_retry ON jobs(retry_of_job_id);

CREATE TABLE transcription_chunks (
  id                INTEGER PRIMARY KEY,
  source_stream_id  INTEGER NOT NULL REFERENCES source_streams(id) ON DELETE CASCADE,
  chunk_index       INTEGER NOT NULL CHECK (chunk_index >= 0),
  start_ms          INTEGER NOT NULL CHECK (start_ms >= 0),
  end_ms            INTEGER NOT NULL CHECK (end_ms > start_ms),
  audio_path        TEXT,
  status            TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','done','failed')),
  provider          TEXT,
  attempts          INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
  created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  updated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  UNIQUE (source_stream_id, start_ms)
);

CREATE TABLE transcript_segments (
  id                INTEGER PRIMARY KEY,
  source_stream_id  INTEGER NOT NULL REFERENCES source_streams(id) ON DELETE CASCADE,
  chunk_id          INTEGER NOT NULL REFERENCES transcription_chunks(id) ON DELETE CASCADE,
  start_ms          INTEGER NOT NULL CHECK (start_ms >= 0),
  end_ms            INTEGER NOT NULL CHECK (end_ms >= start_ms),
  speaker           TEXT,
  language          TEXT,
  text              TEXT NOT NULL,
  created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX ix_segments_stream ON transcript_segments(source_stream_id, start_ms);
CREATE INDEX ix_segments_chunk ON transcript_segments(chunk_id);

CREATE TABLE transcript_words (
  id                INTEGER PRIMARY KEY,
  source_stream_id  INTEGER NOT NULL REFERENCES source_streams(id) ON DELETE CASCADE,
  segment_id        INTEGER NOT NULL REFERENCES transcript_segments(id) ON DELETE CASCADE,
  start_ms          INTEGER NOT NULL CHECK (start_ms >= 0),
  end_ms            INTEGER NOT NULL CHECK (end_ms >= start_ms),
  word              TEXT NOT NULL CHECK (length(word) >= 1),
  confidence        REAL CHECK (confidence BETWEEN 0 AND 1)
);
CREATE INDEX ix_words_stream ON transcript_words(source_stream_id, start_ms);
CREATE INDEX ix_words_segment ON transcript_words(segment_id);

CREATE TABLE chat_messages (
  id                INTEGER PRIMARY KEY,
  source_stream_id  INTEGER NOT NULL REFERENCES source_streams(id) ON DELETE CASCADE,
  offset_ms         INTEGER NOT NULL,
  author            TEXT,
  message           TEXT NOT NULL,
  is_reaction       INTEGER NOT NULL DEFAULT 0 CHECK (is_reaction IN (0,1)),
  kind              TEXT NOT NULL DEFAULT 'text' CHECK (kind IN ('text','donation','membership','other'))
);
CREATE INDEX ix_chat_stream ON chat_messages(source_stream_id, offset_ms);

CREATE TABLE highlight_windows (
  id                      INTEGER PRIMARY KEY,
  source_stream_id        INTEGER NOT NULL REFERENCES source_streams(id) ON DELETE CASCADE,
  start_ms                INTEGER NOT NULL CHECK (start_ms >= 0),
  end_ms                  INTEGER NOT NULL CHECK (end_ms > start_ms),
  audio_signal            REAL NOT NULL CHECK (audio_signal BETWEEN 0 AND 1),
  chat_signal             REAL CHECK (chat_signal BETWEEN 0 AND 1),
  preselected             INTEGER NOT NULL DEFAULT 0 CHECK (preselected IN (0,1)),
  llm_score               INTEGER CHECK (llm_score BETWEEN 0 AND 100),
  llm_category            TEXT CHECK (llm_category IN ('lucu','hype','kontroversial','informatif','emosional','lainnya')),
  llm_reason              TEXT CHECK (length(llm_reason) <= 200),
  llm_suggested_start_ms  INTEGER,
  llm_suggested_end_ms    INTEGER,
  llm_suggested_title     TEXT CHECK (length(llm_suggested_title) <= 100),
  llm_status              TEXT NOT NULL DEFAULT 'not_requested' CHECK (llm_status IN ('not_requested','done','invalid','failed')),
  created_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  updated_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  UNIQUE (source_stream_id, start_ms)
);
CREATE INDEX ix_windows_preselected ON highlight_windows(source_stream_id, preselected);

CREATE TABLE cam_regions (
  id                INTEGER PRIMARY KEY,
  channel_id        INTEGER REFERENCES channels(id) ON DELETE CASCADE,
  source_stream_id  INTEGER REFERENCES source_streams(id) ON DELETE CASCADE,
  clip_id           INTEGER REFERENCES clips(id) ON DELETE CASCADE,
  role              TEXT NOT NULL CHECK (role IN ('cam','content','face_a','face_b')),
  x                 REAL NOT NULL CHECK (x BETWEEN 0 AND 1),
  y                 REAL NOT NULL CHECK (y BETWEEN 0 AND 1),
  w                 REAL NOT NULL CHECK (w BETWEEN 0.05 AND 1),
  h                 REAL NOT NULL CHECK (h BETWEEN 0.05 AND 1),
  confidence        REAL CHECK (confidence BETWEEN 0 AND 1),
  created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  updated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  CHECK (x + w <= 1.0001 AND y + h <= 1.0001),
  CHECK ((channel_id IS NOT NULL) + (source_stream_id IS NOT NULL) + (clip_id IS NOT NULL) = 1)
);
CREATE INDEX ix_regions_channel ON cam_regions(channel_id);
CREATE INDEX ix_regions_stream ON cam_regions(source_stream_id);
CREATE INDEX ix_regions_clip ON cam_regions(clip_id);
-- satu region per role per pemilik
CREATE UNIQUE INDEX ux_regions_channel_role ON cam_regions(channel_id, role) WHERE channel_id IS NOT NULL;
CREATE UNIQUE INDEX ux_regions_stream_role  ON cam_regions(source_stream_id, role) WHERE source_stream_id IS NOT NULL;
CREATE UNIQUE INDEX ux_regions_clip_role    ON cam_regions(clip_id, role) WHERE clip_id IS NOT NULL;

CREATE TABLE settings (
  key         TEXT PRIMARY KEY,
  value       TEXT NOT NULL CHECK (json_valid(value)),
  updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
