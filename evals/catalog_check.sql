SELECT t AS missing_table
FROM (
  SELECT 'users' AS t UNION ALL SELECT 'teams' UNION ALL SELECT 'entities'
  UNION ALL SELECT 'documents' UNION ALL SELECT 'property_definitions'
  UNION ALL SELECT 'channels' UNION ALL SELECT 'channel_messages'
  UNION ALL SELECT 'reminders' UNION ALL SELECT 'mentions'
  UNION ALL SELECT 'bots' UNION ALL SELECT 'schema_migrations'
) x
WHERE NOT EXISTS (
  SELECT 1 FROM sqlite_master m WHERE m.type='table' AND m.name=x.t
);
