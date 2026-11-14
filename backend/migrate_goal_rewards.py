"""Apply additive goal-reward schema changes to the configured database.

Run: backend/.venv/bin/python backend/migrate_goal_rewards.py
"""
from sqlalchemy import inspect, text
from database import engine
from db_models import GoalReward


def migrate():
    columns = {column['name'] for column in inspect(engine).get_columns('users')}
    if 'invited_by' not in columns:
        with engine.begin() as connection:
            connection.execute(text(
                'ALTER TABLE users ADD COLUMN invited_by INT NULL, '
                'ADD CONSTRAINT fk_users_invited_by FOREIGN KEY (invited_by) '
                'REFERENCES users(id) ON DELETE SET NULL'
            ))
    GoalReward.__table__.create(engine, checkfirst=True)


if __name__ == '__main__':
    migrate()
    print('Goal reward schema ready. Existing records preserved.')
