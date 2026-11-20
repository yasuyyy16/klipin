-- Disalin dari docs/spec/05-database.md §6.2 (v1.2); INSERT diganti INSERT OR IGNORE
-- agar idempoten dan tidak menimpa nilai yang sudah diubah Pengguna.
INSERT OR IGNORE INTO layout_presets (code, name, is_builtin, params) VALUES
 ('gaming',      'Gaming (cam atas)',       1, '{"cam_height_pct":35}'),
 ('podcast',     'Podcast (ikuti pembicara)',1, '{"switch_hold_ms":1500}'),
 ('irl',         'IRL (ikuti wajah)',       1, '{"max_pan_pct_per_s":5}'),
 ('split_two',   'Dua Orang (atas-bawah)',  1, '{"split_pct":50}'),
 ('center_crop', 'Crop Tengah',             1, '{}'),
 ('custom',      'Kustom',                  1, '{}');

INSERT OR IGNORE INTO subtitle_styles (name, is_builtin, mode, font_size, uppercase, max_words_per_line, position_pct) VALUES
 ('Sederhana',      1, 'sentence',       56, 0, 3, 75),
 ('Highlight Kata', 1, 'word_highlight', 68, 0, 3, 70),
 ('Besar Tengah',   1, 'word_highlight', 96, 1, 2, 55);

INSERT OR IGNORE INTO settings (key, value) VALUES
 ('score_weights',            '{"audio":0.30,"chat":0.20,"llm":0.50}'),   -- BR-001
 ('score_min_threshold',      '40'),                                      -- BR-006
 ('chat_delay_ms',            '8000'),                                    -- FR-010
 ('chat_reaction_words',      '["wkwk","wkwkwk","awokawok","anjir","anjay","gg","kekw","lol","lmao","pog","omegalul","😂","🤣"]'),
 ('live_segment_seconds',     '10'),
 ('live_block_minutes',       '5'),                                       -- FR-013
 ('live_last_n_default_s',    '60'),                                      -- FR-004
 ('max_heavy_jobs',           '1'),
 ('confirm_usage_over_min',   '30'),                                      -- FR-022
 ('max_audio_minutes_per_job','600'),
 ('transcriber_provider',     '"deepgram"'),
 ('llm_provider',             '"anthropic"'),
 ('llm_models',               '{"judge_highlight":null,"translate_lines":null,"write_captions":null}'),  -- diisi nama model saat setup (07-integrasi.md INT-05)
 ('kick_live_chat_enabled',   'false'),                                   -- INT-03 eksperimental
 ('default_subtitle_style',   '"Highlight Kata"'),
 ('output_dir',               '"output"'),
 ('download_max_height',      '1080'),
 ('upload_default_mode',      '"manual"'),                                -- F-16
 ('caption_templates',        '{"youtube":"","tiktok":"","instagram":"","facebook":""}'),  -- FR-027, teks tetap di akhir caption
 ('upload_platforms_enabled', '["youtube","tiktok","instagram","facebook"]'),
 ('manual_upload_urls',       '{"youtube":"https://studio.youtube.com","tiktok":"https://www.tiktok.com/upload","instagram":"https://www.instagram.com","facebook":"https://business.facebook.com"}');  -- INT-13
