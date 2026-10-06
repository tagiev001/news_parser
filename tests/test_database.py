import unittest
from contextlib import nullcontext
from unittest.mock import MagicMock, Mock, patch

from src import database


class DatabaseSchemaTests(unittest.TestCase):
    def test_each_schema_initializes_only_its_own_tables(self):
        schemas_and_other_schema_names = (
            (database.NEWS_SCHEMA, (database.COMMENTS_SCHEMA, database.STATISTICS_SCHEMA)),
            (database.COMMENTS_SCHEMA, (database.NEWS_SCHEMA, database.STATISTICS_SCHEMA)),
            (database.STATISTICS_SCHEMA, (database.NEWS_SCHEMA, database.COMMENTS_SCHEMA)),
        )
        for schema_name, other_schema_names in schemas_and_other_schema_names:
            with self.subTest(schema=schema_name):
                connection = Mock()
                connection.transaction.return_value = nullcontext()
                connection_context = MagicMock()
                connection_context.__enter__.return_value = connection

                with (
                    patch.object(database.psycopg, "connect", return_value=connection_context),
                    patch.object(database, "_initialized_schemas", set()),
                ):
                    with database.get_connection(schema_name):
                        pass

                executed_statements = [
                    call.args[0] for call in connection.execute.call_args_list
                ]
                self.assertIn(
                    database.sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                        database.sql.Identifier(schema_name)
                    ),
                    executed_statements,
                )
                self.assertIn(
                    database.sql.SQL("SET LOCAL search_path TO {}").format(
                        database.sql.Identifier(schema_name)
                    ),
                    executed_statements,
                )
                self.assertIn(
                    database.sql.SQL("SET search_path TO {}").format(
                        database.sql.Identifier(schema_name)
                    ),
                    executed_statements,
                )
                other_statements = tuple(
                    statement
                    for other_schema_name in other_schema_names
                    for statement in database.SCHEMA_STATEMENTS[other_schema_name]
                )
                for statement in database.SCHEMA_STATEMENTS[schema_name]:
                    self.assertIn(statement, executed_statements)
                for statement in other_statements:
                    self.assertNotIn(statement, executed_statements)

    def test_unknown_schema_is_rejected(self):
        with patch.object(database.psycopg, "connect") as connect:
            with self.assertRaisesRegex(ValueError, "Unknown database schema"):
                with database.get_connection("public"):
                    pass
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
