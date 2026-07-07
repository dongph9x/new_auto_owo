"""Backend tests for battle logging storage and dashboard API."""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

# Project root on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import utils.history_tracker as ht
from cogs.battle_logger import parse_loss_streak
from dashboard.app import app


class StreakParseTest(unittest.TestCase):
    def test_from_message_text(self):
        self.assertEqual(parse_loss_streak("You lost your **12** win streak!"), 12)
        self.assertEqual(parse_loss_streak("streak: 5"), 5)
        self.assertEqual(parse_loss_streak("lost your 0 win streak"), 0)

    def test_from_json_fallback(self):
        self.assertEqual(parse_loss_streak("you lost", {"streak": 7}), 7)
        self.assertEqual(parse_loss_streak("you lost", {"player": {"winStreak": 3}}), 3)


class BattleStorageTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db_path = self._tmp.name
        self._patcher = patch.object(ht, "HISTORY_FILE", self.db_path)
        self._patcher.start()
        ht.init_db()

    def tearDown(self):
        self._patcher.stop()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def test_record_and_query_battles(self):
        sample_json = {"teams": [{"name": "player"}, {"name": "enemy"}], "result": "lose"}
        ht.record_battle("111", "lose", streak=3, uuid="aaaa-bbbb", battle_link="https://owobot.com/battle-log?uuid=aaaa-bbbb", raw_json=sample_json)
        ht.record_battle("111", "win", streak=4, uuid="cccc-dddd", battle_link="https://owobot.com/battle-log?uuid=cccc-dddd")
        ht.record_battle("222", "win", streak=1)

        counts = ht.get_battle_result_counts("111")
        self.assertEqual(counts["wins"], 1)
        self.assertEqual(counts["loses"], 1)
        self.assertEqual(counts["total"], 2)
        self.assertEqual(counts["win_rate"], 50.0)

        losses = ht.get_recent_battles("111", limit=10, result="lose")
        self.assertEqual(len(losses), 1)
        self.assertIsNotNone(losses[0]["id"])
        self.assertEqual(losses[0]["streak"], 3)
        self.assertEqual(losses[0]["raw_json"]["teams"][0]["name"], "player")

        by_id = ht.get_battles_by_ids("111", [losses[0]["id"]])
        self.assertEqual(len(by_id), 1)
        self.assertEqual(by_id[0]["id"], losses[0]["id"])

        recent = ht.get_recent_battles("111", limit=1)
        self.assertEqual(recent[0]["result"], "win")


class BattleAPITest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self.db_path = self._tmp.name
        self.db_patcher = patch.object(ht, "HISTORY_FILE", self.db_path)
        self.db_patcher.start()
        ht.init_db()
        ht.record_battle("999", "lose", streak=2, uuid="u1", battle_link="https://owobot.com/battle-log?uuid=u1", raw_json={"turns": 5})
        ht.record_battle("999", "win", streak=3)

        app.config["TESTING"] = True
        self.client = app.test_client()
        self.token = "test-control-token"
        self.auth_patcher = patch(
            "dashboard.app.load_auth_config",
            return_value={"control_api_token": self.token},
        )
        self.auth_patcher.start()

    def tearDown(self):
        self.auth_patcher.stop()
        self.db_patcher.stop()
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_battles_list_api(self):
        r = self.client.get("/api/battles?id=999&limit=5", headers=self._headers())
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data["counts"]["wins"], 1)
        self.assertEqual(data["counts"]["loses"], 1)
        self.assertEqual(len(data["battles"]), 2)
        links = [b["battle_link"] for b in data["battles"] if b.get("battle_link")]
        self.assertEqual(len(links), 1)
        self.assertIn("owobot.com/battle-log", links[0])

    def test_battles_list_requires_auth(self):
        r = self.client.get("/api/battles?id=999")
        self.assertEqual(r.status_code, 401)

    def test_analyze_api_without_key(self):
        with patch("dashboard.app._account_battle_analysis_cfg", return_value={}):
            r = self.client.get("/api/battles/analyze?id=999", headers=self._headers())
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertFalse(data["success"])
        self.assertIn("api key", data["error"].lower())

    def test_analyze_api_success(self):
        cfg = {"ai_provider": "openai", "ai_api_key": "sk-test", "ai_model": "gpt-4o-mini"}
        with patch("dashboard.app._account_battle_analysis_cfg", return_value=cfg):
            with patch("dashboard.app._run_battle_analysis", return_value=("Thua vì level thấp.", None)):
                r = self.client.get("/api/battles/analyze?id=999", headers=self._headers())
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data["success"])
        self.assertIn("level", data["summary"].lower())

    def test_analyze_by_battle_id(self):
        loss = ht.get_recent_battles("999", result="lose")[0]
        bid = loss["id"]
        cfg = {"ai_provider": "openai", "ai_api_key": "sk-test", "ai_model": "gpt-4o-mini"}

        def fake_run(cfg, battles, counts, specific=False):
            self.assertTrue(specific)
            self.assertEqual(len(battles), 1)
            self.assertEqual(battles[0]["id"], bid)
            return ("Phân tích log #{}".format(bid), None)

        with patch("dashboard.app._account_battle_analysis_cfg", return_value=cfg):
            with patch("dashboard.app._run_battle_analysis", side_effect=fake_run):
                r = self.client.get(f"/api/battles/analyze?id=999&battle_id={bid}", headers=self._headers())
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["battle_ids"], [bid])

    def test_analyze_missing_battle_id(self):
        r = self.client.get("/api/battles/analyze?id=999&battle_id=99999", headers=self._headers())
        data = r.get_json()
        self.assertFalse(data["success"])
        self.assertIn("not found", data["error"].lower())


if __name__ == "__main__":
    unittest.main()

