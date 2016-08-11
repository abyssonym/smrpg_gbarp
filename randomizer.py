from randomtools.tablereader import TableObject
from randomtools.utils import (
    classproperty, mutate_normal, shuffle_bits,
    utilrandom as random)
from randomtools.interface import (
    get_outfile, get_seed, get_flags, run_interface, rewrite_snes_meta,
    clean_and_write, finish_interface)
from collections import defaultdict
from os import path


VERSION = 1
ALL_OBJECTS = None


class CharIndexObject:
    @property
    def level(self):
        return (self.index / 5) + 2

    @property
    def character_id(self):
        return self.index % 5

    @classmethod
    def get_by_character(cls, character, index):
        candidates = [c for c in cls.every if c.character_id == character]
        return candidates[index]


class StatObject(CharIndexObject):
    @property
    def attack(self):
        return self.physical >> 4

    @property
    def defense(self):
        return self.physical & 0xF

    @property
    def magic_attack(self):
        return self.magical >> 4

    @property
    def magic_defense(self):
        return self.magical & 0xF

    def set_stat(self, attr, value):
        assert 0 <= value <= 0xF
        if attr == "max_hp":
            self.max_hp = value
            return

        if attr in ["attack", "defense"]:
            affected = "physical"
        elif attr in ["magic_attack", "magic_defense"]:
            affected = "magical"

        oldvalue = getattr(self, affected)
        if attr in ["attack", "magic_attack"]:
            newvalue = (oldvalue & 0xF) | (value << 4)
        elif attr in ["defense", "magic_defense"]:
            newvalue = (oldvalue & 0xF0) | value

        setattr(self, affected, newvalue)


class MonsterObject(TableObject):
    flag = "m"
    flag_description = "enemies"
    mutate_attributes = {
        "hp": (1, 32000),
        "speed": None,
        "attack": None,
        "defense": None,
        "magic_attack": None,
        "magic_defense": None,
        "fp": None,
        "evade": None,
        "magic_evade": None
        }
    intershuffle_attributes = [
            "hp", "speed", "attack", "defense", "magic_attack",
            "magic_defense", "fp", "evade", "magic_evade", "resistances",
            "immunities", "weaknesses_approach", "coin_anim_entrance",
        ]

    @property
    def rank(self):
        hp = self.hp if self.hp >= 10 else 100
        return hp * max(self.attack, self.magic_attack, 1)

    @property
    def intershuffle_valid(self):
        return not self.is_boss and self.rank >= 550

    @property
    def is_boss(self):
        return self.hit_special_defense & 0x02

    @classmethod
    def intershuffle(cls):
        super(MonsterObject, cls).intershuffle()
        valid = [m for m in cls.every if m.intershuffle_valid]
        hitspecs = [m.hit_special_defense & 0xFC for m in valid]
        random.shuffle(hitspecs)
        for hs, m in zip(hitspecs, valid):
            m.hit_special_defense = (m.hit_special_defense & 0x03) | hs

    def mutate(self):
        oldstats = {}
        for key in self.mutate_attributes:
            oldstats[key] = getattr(self, key)
        super(MonsterObject, self).mutate()
        if self.is_boss:
            for (attr, oldval) in oldstats.items():
                if getattr(self, attr) < oldval:
                    setattr(self, attr, oldval)


class MonsterAttackObject(TableObject): pass
class MonsterRewardObject(TableObject): pass
class PackObject(TableObject): pass
class FormationObject(TableObject): pass


class CharacterObject(TableObject):
    flag = "c"
    flag_description = "character stats"

    mutate_attributes = {"speed": (1, 0xFF),
                         "level": (1, 30),
                         }
    intershuffle_attributes = ["speed"]

    def cleanup(self):
        self.current_hp = self.max_hp

        my_learned = [l for l in LearnObject.every if l.level <= self.level
                      and l.character_id == self.index]
        for l in my_learned:
            if l.spell <= 0x1A:
                self.known_spells |= (1 << l.spell)

        my_growths = [s for s in StatGrowthObject.every if
                      s.level <= self.level and s.character_id == self.index]
        for g in my_growths:
            for attr in ["max_hp", "attack", "defense",
                         "magic_attack", "magic_defense"]:
                setattr(self, attr, getattr(self, attr) + getattr(g, attr))

        if self.level == 1:
            self.xp = 0
        else:
            self.xp = LevelUpXPObject.get(self.level-2).xp


class ItemObject(TableObject): pass
class PriceObject(TableObject): pass
class LevelUpXPObject(TableObject): pass


class StatGrowthObject(StatObject, TableObject):
    flag = "c"

    @classmethod
    def full_randomize(cls):
        if hasattr(cls, "after_order"):
            for cls2 in cls.after_order:
                if not (hasattr(cls2, "randomized") and cls2.randomized):
                    raise Exception("Randomize order violated.")
        attributes = ["max_hp", "attack", "defense",
                      "magic_attack", "magic_defense"]
        curves = defaultdict(list)
        for character_index in range(5):
            c = CharacterObject.get(character_index)
            for attr in attributes:
                value = getattr(c, attr)
                for l in cls.every:
                    if l.character_id == c.index and l.level <= 20:
                        value += getattr(l, attr)
                value = mutate_normal(value, maximum=999)
                fixed_points = [(1, 0), (20, value)]
                for _ in xrange(3):
                    dex = random.randint(1, len(fixed_points)-1)
                    lower_level, lower_value = fixed_points[dex-1]
                    upper_level, upper_value = fixed_points[dex]
                    if upper_level - lower_level < 4:
                        continue
                    level_interval = (upper_level - lower_level) / 2
                    value_interval = (upper_value - lower_value) / 2
                    level = (lower_level + random.randint(0, level_interval)
                             + random.randint(0, level_interval))
                    if level <= lower_level or level >= upper_level:
                        continue
                    value = (lower_value + random.randint(0, value_interval)
                             + random.randint(0, value_interval))
                    fixed_points.append((level, value))
                    fixed_points = sorted(fixed_points)

                for ((l1, v1), (l2, v2)) in zip(fixed_points, fixed_points[1:]):
                    ldist = l2 - l1
                    vdist = v2 - v1
                    for l in range(l1+1, l2):
                        factor = (l - l1) / float(ldist)
                        v = v1 + (factor * vdist)
                        fixed_points.append((l, int(round(v))))
                fixed_points = sorted(fixed_points)
                levels, values = zip(*fixed_points)
                assert len(fixed_points) == 20
                assert levels == tuple(sorted(levels))
                assert values == tuple(sorted(values))
                increases = []
                for v1, v2 in zip(values, values[1:]):
                    increases.append(v2-v1)

                frontload_factor = random.random() * random.random()
                if attr in ["defense", "magic_defense"]:
                    frontload_factor *= random.random()
                frontloaded = 0
                for n, inc in enumerate(increases):
                    max_index = len(increases) - 1
                    factor = (((max_index-n) / float(max_index))
                              * frontload_factor)
                    amount = int(round(inc * factor))
                    frontloaded += amount
                    increases[n] = (inc - amount)
                frontloaded = max(frontloaded, 1)

                while max(increases) > 15:
                    i = increases.index(max(increases))
                    increases[i] = increases[i] - 1
                    choices = [n for (n, v) in enumerate(increases) if v < 15]
                    if random.randint(0, len(choices)) == 0:
                        frontloaded += 1
                    elif choices:
                        i = random.choice(choices)
                        increases[i] = increases[i] + 1

                curves[attr].append((frontloaded, increases))

        for attr in attributes:
            attr_curves = curves[attr]
            random.shuffle(attr_curves)
            for character_index in xrange(5):
                (base, increases) = attr_curves.pop()
                c = CharacterObject.get(character_index)
                if c.index == 0 and attr in ["max_hp", "attack"]:
                    # ensure basic starting stats for Mario
                    while base < 20:
                        base += 1
                        for i in range(len(increases)):
                            if increases[i] > 0:
                                increases[i] = increases[i] - 1
                                break
                getattr(c, attr)
                setattr(c, attr, base)
                assert len(increases) == 19
                for s in StatGrowthObject.every:
                    if s.character_id == c.index:
                        if increases:
                            s.set_stat(attr, increases.pop(0))
                        else:
                            s.set_stat(attr, mutate_normal(2))


class StatBonusObject(StatObject, TableObject):
    flag = "c"
    intershuffle_attributes = ["max_hp", "physical", "magical"]

    @property
    def intershuffle_valid(self):
        return self.level <= 20

    def mutate(self):
        valids = [s for s in StatBonusObject.every if s.intershuffle_valid and
                  all([getattr(s, attr)
                       for attr in self.intershuffle_attributes])]
        for attr in self.intershuffle_attributes:
            while getattr(self, attr) == 0:
                setattr(self, attr, getattr(random.choice(valids), attr))


class SpellObject(TableObject): pass


class LearnObject(CharIndexObject, TableObject):
    flag = "s"
    flag_description = "character spells"

    @property
    def rank(self):
        return self.level

    @classmethod
    def full_randomize(cls):
        if hasattr(cls, "after_order"):
            for cls2 in cls.after_order:
                if not (hasattr(cls2, "randomized") and cls2.randomized):
                    raise Exception("Randomize order violated.")
        for c in CharacterObject.every:
            c.known_spells = 0
        spells = range(0x1b)
        random.shuffle(spells)
        supplemental = random.sample(spells, 3)
        spells = spells + supplemental
        charspells = defaultdict(list)
        while spells:
            valid = [i for i in range(5) if len(charspells[i]) < 6]
            chosen = random.choice(valid)
            charspells[chosen].append(spells.pop(0))
        for l in LearnObject.every:
            l.spell = 0xFF
        for i in range(5):
            charlevels = sorted(random.sample(range(2, 20), 5))
            spells = charspells[i]
            c = CharacterObject.get(i)
            c.known_spells |= (1 << spells[0])
            for l, s in zip(charlevels, spells[1:]):
                l = LearnObject.get_by_character(i, l-2)
                l.spell = s
        cls.randomized = True


class WeaponTimingObject(TableObject): pass
class ShopObject(TableObject): pass
class FlowerBonusObject(TableObject): pass


if __name__ == "__main__":
    try:
        print ('You are using the Super Mario RPG '
               'randomizer version %s.' % VERSION)
        ALL_OBJECTS = [g for g in globals().values()
                       if isinstance(g, type) and issubclass(g, TableObject)
                       and g not in [TableObject]]
        run_interface(ALL_OBJECTS, snes=True)
        hexify = lambda x: "{0:0>2}".format("%x" % x)
        numify = lambda x: "{0: >3}".format(x)
        minmax = lambda x: (min(x), max(x))
        clean_and_write(ALL_OBJECTS)
        rewrite_snes_meta("SMRPG-R", VERSION, megabits=32, lorom=True)
        finish_interface()
        import pdb; pdb.set_trace()
    except ValueError, e:
        print "ERROR: %s" % e
        raw_input("Press Enter to close this program.")
