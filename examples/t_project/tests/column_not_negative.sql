-- Column-level SQL test example
-- Checks that a numeric column has no negative values
-- Can be used on any column by referencing @column_name
-- Returns rows when test fails (0 rows = pass)

SELECT @column_name
FROM @table_name
WHERE @column_name < 0
