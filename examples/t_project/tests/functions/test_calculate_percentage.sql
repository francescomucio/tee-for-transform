-- Test for calculate_percentage function
-- This test verifies that the function correctly calculates percentages

-- Test case 1: Normal calculation (10/20 = 50%)
SELECT
    my_schema.calculate_percentage(10.0, 20.0) = 50.0 AS test_passed
