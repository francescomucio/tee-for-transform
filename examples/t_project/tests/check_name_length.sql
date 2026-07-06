-- Check that name column values are not too long (max 100 characters)
-- Returns rows when test fails (0 rows = pass, 1+ rows = fail)

SELECT id, name
FROM @table_name
WHERE LENGTH(name) > 100
