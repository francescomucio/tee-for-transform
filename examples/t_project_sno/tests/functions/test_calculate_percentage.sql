-- Test for calculate_percentage function (Snowflake)
-- This test verifies that the function correctly calculates percentages

SELECT
    my_schema.calculate_percentage(@param1, @param2) AS result
