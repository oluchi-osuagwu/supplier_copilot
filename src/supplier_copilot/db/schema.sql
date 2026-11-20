-- =====================================================================
-- Star schema for the M5 (Walmart) sales data.
--
--   fact tables  = measurable events (units sold, prices)   -> "how much"
--   dim  tables  = descriptive context (what, where, when)  -> "by what"
--
--                 dim_date
--                    |
--   dim_item --- fact_sales --- dim_store
--                    |
--               fact_prices (weekly)
--
-- CREATE OR REPLACE makes the script idempotent: running it twice gives
-- the same result as running it once (safe to rebuild from raw data).
--
-- Note on constraints: primary keys are declared on the small dimension
-- tables. They are NOT declared on the 59M-row fact table, because the
-- index would cost a lot of memory and load time. Fact-table uniqueness
-- and referential integrity are verified by tests instead, which is the
-- common practice in analytical warehouses (Snowflake/BigQuery don't
-- enforce foreign keys either).
-- =====================================================================

-- ---------- Dimension: calendar (one row per day) ----------
CREATE OR REPLACE TABLE dim_date (
    date            DATE     PRIMARY KEY,     -- calendar date, e.g. 2011-01-29
    d               VARCHAR  NOT NULL UNIQUE, -- M5 day code: d_1 ... d_1969 (join key to raw sales)
    wm_yr_wk        INTEGER  NOT NULL,        -- Walmart fiscal week id, e.g. 11101 (join key to prices)
    weekday         VARCHAR  NOT NULL,        -- 'Saturday' ...
    wday            TINYINT  NOT NULL,        -- 1 = Saturday ... 7 = Friday (Walmart week starts Saturday)
    month           TINYINT  NOT NULL,
    year            SMALLINT NOT NULL,
    event_name_1    VARCHAR,                  -- e.g. 'SuperBowl', 'Easter' (NULL when no event)
    event_type_1    VARCHAR,                  -- 'Sporting', 'Cultural', 'National', 'Religious'
    event_name_2    VARCHAR,                  -- a few days have two events
    event_type_2    VARCHAR,
    snap_ca         BOOLEAN  NOT NULL,        -- SNAP (food stamp) benefits paid out that day, per state
    snap_tx         BOOLEAN  NOT NULL,
    snap_wi         BOOLEAN  NOT NULL
);

-- ---------- Dimension: stores (geography hierarchy: state -> store) ----------
CREATE OR REPLACE TABLE dim_store (
    store_id        VARCHAR  PRIMARY KEY,     -- e.g. 'CA_1'
    state_id        VARCHAR  NOT NULL         -- 'CA', 'TX', 'WI'
);

-- ---------- Dimension: items (product hierarchy: category -> department -> item) ----------
CREATE OR REPLACE TABLE dim_item (
    item_id         VARCHAR  PRIMARY KEY,     -- e.g. 'FOODS_3_090'
    dept_id         VARCHAR  NOT NULL,        -- e.g. 'FOODS_3'
    cat_id          VARCHAR  NOT NULL         -- 'FOODS', 'HOBBIES', 'HOUSEHOLD'
);

-- ---------- Fact: daily unit sales (grain = one item, in one store, on one day) ----------
CREATE OR REPLACE TABLE fact_sales (
    item_id         VARCHAR  NOT NULL,
    store_id        VARCHAR  NOT NULL,
    date            DATE     NOT NULL,
    units_sold      INTEGER  NOT NULL
);

-- ---------- Fact: weekly shelf price (grain = one item, in one store, in one fiscal week) ----------
CREATE OR REPLACE TABLE fact_prices (
    item_id         VARCHAR       NOT NULL,
    store_id        VARCHAR       NOT NULL,
    wm_yr_wk        INTEGER       NOT NULL,
    sell_price      DECIMAL(10,2) NOT NULL    -- money as exact DECIMAL, never floating point
);

-- ---------- Convenience view: denormalized daily sales with hierarchy + revenue ----------
-- A view stores the query, not the data. It gives the text-to-SQL agent (week 3)
-- one well-named "table" to query instead of writing 4 joins itself.
-- LEFT JOIN on prices: an item has no price in weeks before it was stocked,
-- so those rows keep their sales (always 0) with a NULL price/revenue.
CREATE OR REPLACE VIEW v_daily_sales AS
SELECT
    s.date,
    cal.year,
    cal.month,
    cal.wm_yr_wk,
    cal.event_name_1,
    s.item_id,
    i.dept_id,
    i.cat_id,
    s.store_id,
    st.state_id,
    s.units_sold,
    p.sell_price,
    s.units_sold * p.sell_price AS revenue
FROM fact_sales  AS s
JOIN dim_item    AS i   ON i.item_id   = s.item_id
JOIN dim_store   AS st  ON st.store_id = s.store_id
JOIN dim_date    AS cal ON cal.date    = s.date
LEFT JOIN fact_prices AS p
       ON p.item_id  = s.item_id
      AND p.store_id = s.store_id
      AND p.wm_yr_wk = cal.wm_yr_wk;
