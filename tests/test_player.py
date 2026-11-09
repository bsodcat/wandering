"""What the weather does to the player's body."""
import unittest

from game.climate import Conditions
from game.player import NORMAL, Player, body_status, expose, feels_like, wet_status


def weather(air=15.0, wind=5.0, precip=0.0, kind="Clear", fog=0.0):
    return Conditions(air=air, cloud=0.5, precip=precip, wind=wind, fog=fog, light=1.0, kind=kind)


class FeelsLikeTests(unittest.TestCase):
    def test_wind_makes_cold_feel_colder(self):
        self.assertLess(feels_like(-5, 40, 0, 0), feels_like(-5, 5, 0, 0) - 5)

    def test_shelter_blocks_the_wind(self):
        self.assertAlmostEqual(feels_like(-5, 40, 0, 1.0), -5)

    def test_being_wet_feels_colder(self):
        self.assertLess(feels_like(10, 0, 100, 0), feels_like(10, 0, 0, 0) - 5)


class ExposureTests(unittest.TestCase):
    def test_a_mild_day_changes_nothing(self):
        p = Player(0, 0)
        expose(p, 8, weather(air=16), shelter=0)
        self.assertAlmostEqual(p.body, NORMAL, places=1)
        self.assertEqual(p.health, 100)

    def test_bitter_cold_kills(self):
        p = Player(0, 0)
        msgs = []
        for _ in range(48):
            msgs += expose(p, 1, weather(air=-25, wind=40, precip=0.8, kind="Blizzard"), shelter=0)
        self.assertFalse(p.alive)
        self.assertEqual(p.cause, "froze to death")
        self.assertIn("You're getting cold.", msgs)
        self.assertIn("You froze to death.", msgs)

    def test_desert_heat_hurts(self):
        p = Player(0, 0)
        expose(p, 12, weather(air=46, wind=0), shelter=0)
        self.assertGreater(p.body, 39)
        self.assertLess(p.health, 100)

    def test_rain_soaks_you_and_sun_dries_you(self):
        p = Player(0, 0)
        expose(p, 2, weather(air=12, precip=0.8, kind="Rain"), shelter=0)
        self.assertGreater(p.wet, 60)
        expose(p, 10, weather(air=25), shelter=0)
        self.assertLess(p.wet, 5)

    def test_shelter_keeps_the_rain_off(self):
        open_ground, forest = Player(0, 0), Player(0, 0)
        expose(open_ground, 2, weather(air=12, precip=0.8, kind="Rain"), shelter=0)
        expose(forest, 2, weather(air=12, precip=0.8, kind="Rain"), shelter=0.6)
        self.assertLess(forest.wet, open_ground.wet)

    def test_indoors_warms_and_dries_you(self):
        p = Player(0, 0, body=34.5, wet=90, health=60)
        expose(p, 8, weather(air=-20, wind=50, precip=1, kind="Blizzard"), shelter=1, indoors=True)
        self.assertGreater(p.body, 36.5)
        self.assertLess(p.wet, 5)
        self.assertGreater(p.health, 60)

    def test_wading_adds_wetness_at_once(self):
        p = Player(0, 0)
        expose(p, 0.1, weather(air=20), shelter=0, soak=50)
        self.assertGreater(p.wet, 40)

    def test_warnings_come_once(self):
        p = Player(0, 0)
        first = expose(p, 3, weather(air=-10, wind=30), shelter=0)
        again = expose(p, 1, weather(air=-10, wind=30), shelter=0)
        self.assertIn("You're getting cold.", first)
        self.assertNotIn("You're getting cold.", again)


class StatusTests(unittest.TestCase):
    def test_words(self):
        self.assertEqual(body_status(37.0), "Comfortable")
        self.assertEqual(body_status(34.0), "Freezing")
        self.assertEqual(body_status(40.0), "Overheating")
        self.assertEqual(wet_status(0), "Dry")
        self.assertEqual(wet_status(90), "Soaked")


if __name__ == "__main__":
    unittest.main()
