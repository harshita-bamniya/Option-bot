-- ============================================================
-- AI Trading Co-Pilot — Schema v1 (spec §7, §13)
-- Safe to run multiple times.
-- ============================================================

-- ---- Users ----
CREATE TABLE IF NOT EXISTS users (
    telegram_chat_id   BIGINT      PRIMARY KEY,
    username           TEXT,
    capital            NUMERIC(14,2) NOT NULL DEFAULT 500000,
    risk_pct           NUMERIC(4,2)  NOT NULL DEFAULT 1.0,
    trade_style        TEXT          NOT NULL DEFAULT 'All',   -- Intraday/Swing/Positional/All
    risk_profile       TEXT          NOT NULL DEFAULT 'Moderate',
    alerts_on          BOOLEAN       NOT NULL DEFAULT TRUE,
    watchlist          TEXT[]        NOT NULL DEFAULT ARRAY['NIFTY','BANKNIFTY']::TEXT[],
    created_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- ---- Market OHLCV (hypertable) ----
CREATE TABLE IF NOT EXISTS market_data (
    ts           TIMESTAMPTZ NOT NULL,
    instrument   TEXT        NOT NULL,
    timeframe    TEXT        NOT NULL,     -- '1m','5m','15m','1h','1d'
    open         DOUBLE PRECISION NOT NULL,
    high         DOUBLE PRECISION NOT NULL,
    low          DOUBLE PRECISION NOT NULL,
    close        DOUBLE PRECISION NOT NULL,
    volume       BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (instrument, timeframe, ts)
);
SELECT create_hypertable('market_data', 'ts', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days');
CREATE INDEX IF NOT EXISTS idx_md_inst_tf_ts ON market_data (instrument, timeframe, ts DESC);

-- ---- Options chain snapshots ----
CREATE TABLE IF NOT EXISTS options_chain (
    ts             TIMESTAMPTZ NOT NULL,
    instrument     TEXT        NOT NULL,
    expiry         DATE        NOT NULL,
    strike         NUMERIC(12,2) NOT NULL,
    option_type    TEXT        NOT NULL,        -- 'CE' | 'PE'
    ltp            DOUBLE PRECISION,
    bid            DOUBLE PRECISION,
    ask            DOUBLE PRECISION,
    iv             DOUBLE PRECISION,
    oi             BIGINT,
    oi_change      BIGINT,
    volume         BIGINT,
    delta          DOUBLE PRECISION,
    gamma          DOUBLE PRECISION,
    theta          DOUBLE PRECISION,
    vega           DOUBLE PRECISION,
    PRIMARY KEY (instrument, expiry, strike, option_type, ts)
);
SELECT create_hypertable('options_chain', 'ts', if_not_exists => TRUE, chunk_time_interval => INTERVAL '7 days');

-- ---- Daily IV Dataset (spec §6.1) ----
CREATE TABLE IF NOT EXISTS iv_history (
    instrument       TEXT        NOT NULL,
    date             DATE        NOT NULL,
    iv_close         DOUBLE PRECISION NOT NULL,
    atm_strike       NUMERIC(12,2),
    spot_close       DOUBLE PRECISION,
    days_to_expiry   INTEGER,
    vix_close        DOUBLE PRECISION,
    pcr_oi           DOUBLE PRECISION,
    max_pain         NUMERIC(12,2),
    PRIMARY KEY (instrument, date)
);

-- ---- News log ----
CREATE TABLE IF NOT EXISTS news_log (
    id               BIGSERIAL PRIMARY KEY,
    ts               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    instrument       TEXT,
    headline         TEXT NOT NULL,
    source           TEXT,
    url              TEXT,
    sentiment_score  DOUBLE PRECISION,
    impact           TEXT,        -- HIGH | MEDIUM | LOW
    raw              JSONB
);
CREATE INDEX IF NOT EXISTS idx_news_ts  ON news_log (ts DESC);
CREATE INDEX IF NOT EXISTS idx_news_ins ON news_log (instrument, ts DESC);

-- ---- Per-analysis features log (spec §13) ----
CREATE TABLE IF NOT EXISTS features_log (
    ts           TIMESTAMPTZ NOT NULL,
    instrument   TEXT        NOT NULL,
    timeframe    TEXT        NOT NULL,
    features     JSONB       NOT NULL,
    PRIMARY KEY (instrument, timeframe, ts)
);
SELECT create_hypertable('features_log', 'ts', if_not_exists => TRUE, chunk_time_interval => INTERVAL '30 days');

-- ---- Signals (Parts A + B — spec §7.2) ----
CREATE TABLE IF NOT EXISTS trade_signals (
    signal_id            TEXT PRIMARY KEY,
    ts                   TIMESTAMPTZ NOT NULL,
    telegram_chat_id     BIGINT REFERENCES users(telegram_chat_id) ON DELETE SET NULL,
    instrument           TEXT NOT NULL,
    spot_price           DOUBLE PRECISION,
    trade_type           TEXT,
    direction            TEXT,
    fcs_score            DOUBLE PRECISION,
    confidence_pct       DOUBLE PRECISION,
    entry_price          DOUBLE PRECISION,
    stop_loss            DOUBLE PRECISION,
    target_1             DOUBLE PRECISION,
    target_2             DOUBLE PRECISION,
    risk_reward          DOUBLE PRECISION,
    session              TEXT,
    market_regime        TEXT,
    trend_group_score    DOUBLE PRECISION,
    momentum_group_score DOUBLE PRECISION,
    volume_group_score   DOUBLE PRECISION,
    volatility_state     TEXT,
    structure_group_score DOUBLE PRECISION,
    mtfs_score           DOUBLE PRECISION,
    pattern_detected     TEXT,
    pattern_confidence   TEXT,
    iv_rank              DOUBLE PRECISION,
    iv_percentile        DOUBLE PRECISION,
    pcr                  DOUBLE PRECISION,
    news_sentiment_score DOUBLE PRECISION,
    macro_event_flag     BOOLEAN,
    vix_level            DOUBLE PRECISION,
    raw_context          JSONB
);
CREATE INDEX IF NOT EXISTS idx_sig_ts ON trade_signals (ts DESC);
CREATE INDEX IF NOT EXISTS idx_sig_user_ts ON trade_signals (telegram_chat_id, ts DESC);

-- ---- Trade outcomes (Part C — spec §7.2) ----
CREATE TABLE IF NOT EXISTS trade_outcomes (
    signal_id            TEXT PRIMARY KEY REFERENCES trade_signals(signal_id) ON DELETE CASCADE,
    outcome_label        TEXT,    -- WIN | LOSS | PARTIAL | SKIPPED
    exit_price           DOUBLE PRECISION,
    exit_ts              TIMESTAMPTZ,
    actual_pnl_pts       DOUBLE PRECISION,
    actual_pnl_rs        DOUBLE PRECISION,
    max_adverse_excursion DOUBLE PRECISION,
    t1_hit               BOOLEAN,
    t2_hit               BOOLEAN,
    sl_hit               BOOLEAN,
    holding_period_hrs   DOUBLE PRECISION,
    notes                TEXT
);

-- ---- Learning engine weight versions ----
CREATE TABLE IF NOT EXISTS learning_weights (
    version_id       SERIAL PRIMARY KEY,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    weights          JSONB       NOT NULL,
    sample_size      INTEGER,
    holdout_win_rate DOUBLE PRECISION,
    active           BOOLEAN     NOT NULL DEFAULT FALSE,
    notes            TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS uniq_active_weights
    ON learning_weights (active) WHERE active = TRUE;

-- ---- Market context (pre-market briefs, events) ----
CREATE TABLE IF NOT EXISTS market_context (
    date         DATE PRIMARY KEY,
    payload      JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---- Alerts log ----
CREATE TABLE IF NOT EXISTS alerts_log (
    id               BIGSERIAL PRIMARY KEY,
    ts               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    alert_type       TEXT NOT NULL,
    instrument       TEXT,
    telegram_chat_id BIGINT,
    payload          JSONB
);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts_log (ts DESC);
