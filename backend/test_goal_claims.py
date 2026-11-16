"""Exercise goal claims through HTTP validation using an isolated database."""
import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from db_models import User, Report, QuizPass, Friendship
from main import app, get_current_user, _goal_progress, GoalKey


class GoalClaimTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.user = User(email='a@vt.edu', password_hash='unused', display_name='A', major='Physics')
        friend = User(email='b@vt.edu', password_hash='unused', display_name='B', major='Computer Science')
        self.db.add_all([self.user, friend])
        self.db.flush()
        for index in range(3):
            self.db.add(Report(user_id=self.user.id, photo_hash=str(index), stored_name='test.jpg',
                               review_status='approved', lat=37, lng=-80,
                               created_at=datetime.now(timezone.utc).replace(tzinfo=None)))
        self.db.add(QuizPass(user_id=self.user.id, lesson_index=0))
        self.db.add(Friendship(requester_id=self.user.id, addressee_id=friend.id, status='accepted'))
        self.db.commit()
        self.previous_overrides = app.dependency_overrides.copy()
        app.dependency_overrides[get_db] = lambda: self.db
        app.dependency_overrides[get_current_user] = lambda: self.user
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(self.previous_overrides)
        self.db.close()
        self.engine.dispose()

    def claim(self, key, period):
        return self.client.post('/api/me/goals/claim', json={'goal_key': key, 'period': period},
                                headers={'X-Requested-With': 'VT-Lanternfly'})

    def test_every_displayed_goal_can_be_claimed_exactly_once(self):
        goals = _goal_progress(self.db, self.user.id)
        self.assertEqual({goal['key'] for goal in goals}, {key.value for key in GoalKey})
        points = 0
        for goal in goals:
            with self.subTest(goal=goal['key']):
                response = self.claim(goal['key'], goal['period'])
                self.assertEqual(response.status_code, 200, response.text)
                points += 10
                self.assertEqual(response.json()['points'], points)
                claimed = next(g for g in response.json()['goals'] if g['key'] == goal['key'])
                self.assertTrue(claimed['rewarded'])
                repeated = self.claim(goal['key'], goal['period'])
                self.assertEqual(repeated.status_code, 200, repeated.text)
                self.assertEqual(repeated.json()['points'], points)

    def test_invalid_or_retired_goal_is_rejected(self):
        for key in ['egg_mass', 'unknown']:
            self.assertEqual(self.claim(key, 'all-time').status_code, 422)

    def test_incomplete_goal_and_stale_period_are_rejected(self):
        self.db.query(Friendship).delete()
        self.db.commit()
        self.assertEqual(self.claim('invite', 'all-time').status_code, 400)
        self.assertEqual(self.claim('report_3', '2000-01-01').status_code, 409)


if __name__ == '__main__':
    unittest.main()
