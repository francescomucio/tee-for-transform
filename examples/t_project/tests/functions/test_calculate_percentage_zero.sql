-- Test for calculate_percentage function with zero denominator
-- This test verifies that the function returns NULL when denominator is zero

SELECT
    my_schema.calculate_percentage(@param1, @param2) IS NULL AS test_passed
