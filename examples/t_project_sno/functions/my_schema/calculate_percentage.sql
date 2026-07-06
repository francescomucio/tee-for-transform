-- Simple UDF function to calculate percentage (Snowflake version)
-- Usage: SELECT calculate_percentage(25, 100) -- returns 25.0

CREATE OR REPLACE FUNCTION calculate_percentage(
    numerator FLOAT,
    denominator FLOAT
) RETURNS FLOAT AS $$
    SELECT
        CASE
            WHEN denominator = 0 OR denominator IS NULL THEN NULL
            ELSE (numerator / denominator) * 100.0
        END
$$;
