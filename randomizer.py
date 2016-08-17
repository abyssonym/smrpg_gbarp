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
LEVEL_STATS = ["max_hp", "attack", "defense", "magic_attack", "magic_defense"]
EQUIP_STATS = ["speed", "attack", "defense", "magic_attack", "magic_defense"]


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
    flag_description = "monsters"
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
            "magic_defense", "evade", "magic_evade", "resistances",
            "immunities", "weaknesses_approach", "coin_anim_entrance",
        ]

    @property
    def name(self):
        return MonsterNameObject.get(self.index).name

    @property
    def rank(self):
        hp = self.hp if self.hp >= 10 else 100
        return hp * max(self.attack, self.magic_attack, 1)

    @property
    def intershuffle_valid(self):
        return not self.is_boss

    @property
    def immune_death(self):
        return self.hit_special_defense & 0x02

    @property
    def morph_chance(self):
        return self.hit_special_defense & 0x0C

    @property
    def is_boss(self):
        return self.immune_death and not self.morph_chance

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

        if self.is_boss:
            while True:
                chance = random.randint(0, 3)
                if chance == 0:
                    break
                if chance == 1:
                    self.resistances |= (1 << random.randint(0, 7))
                elif chance == 2:
                    self.immunities |= (1 << random.randint(0, 7))
                elif chance == 3:
                    weak = (1 << random.randint(4, 7))
                    if self.weaknesses_approach & weak:
                        self.weaknesses_approach ^= weak
        else:
            self.resistances = shuffle_bits(self.resistances)
            self.immunities = shuffle_bits(self.immunities)
            weak = shuffle_bits(self.weaknesses_approach >> 4, size=4)
            self.weaknesses_approach &= 0x0F
            self.weaknesses_approach |= (weak << 4)
            if random.randint(1, 3) == 3:
                self.hit_special_defense ^= 0x2
            self.hit_special_defense ^= (random.randint(0, 3) << 2)

    @classmethod
    def full_cleanup(cls):
        smithies = [m for m in MonsterObject.every
                    if m.index in [0xb5, 0xb6, 0xed, 0xee, 0xef]]
        hp = max([m.hp for m in smithies])
        for s in smithies:
            s.hp = hp
        super(MonsterObject, cls).full_cleanup()


class MonsterNameObject(TableObject): pass


class MonsterAttackObject(TableObject):
    flag = "m"
    mutate_attributes = {"hitrate": (1, 100)}
    intershuffle_attributes = ["hitrate", "ailments"]

    @property
    def intershuffle_valid(self):
        return self.ailments

    @property
    def no_damage(self):
        return self.misc_multiplier & 0x50

    @property
    def multiplier(self):
        return self.misc_multiplier & 0xF

    @property
    def hide_digits(self):
        return self.misc_multiplier & 0x20

    def mutate(self):
        if self.multiplier <= 7 and not self.buffs:
            new_multiplier = random.randint(0, random.randint(
                0, random.randint(0, 8)))
            if new_multiplier > self.multiplier:
                self.misc_multiplier = new_multiplier
        if not self.buffs and random.choice([True, False, False]):
            i = random.randint(0, 6)
            if i != 4 or random.randint(1, 10) == 10:
                self.ailments = 1 << i
        if self.buffs and random.choice([True, True, False]):
            self.buffs = random.randint(1, 0xF) << 3

        super(MonsterAttackObject, self).mutate()


class MonsterRewardObject(TableObject): pass
class PackObject(TableObject): pass


class FormationObject(TableObject):
    def __repr__(self):
        present = bin(self.enemies_present)[2:]
        hidden = bin(self.enemies_hidden)[2:]
        present = "{0:0>8}".format(present)
        hidden = "{0:0>8}".format(hidden)
        s = "%x: " % self.index
        for i, (p, h) in enumerate(zip(present, hidden)):
            index, x, y = (getattr(self, "monster%s" % i),
                           getattr(self, "monster%s_x" % i),
                           getattr(self, "monster%s_y" % i))
            m = MonsterObject.get(index)
            if h != "1" and p == "1":
                s += "%x %s (%s, %s); " % (index, m.name.strip(), x, y)
            if h == "1":
                assert p == "1"
                s += "%x %s (hidden, %s, %s); " % (index, m.name.strip(), x, y)
        s = s.strip().rstrip(";").strip()
        return s

    @property
    def enemies(self):
        enemies = bin(self.enemies_present | self.enemies_hidden)[2:]
        enemies = "{0:0>8}".format(enemies)
        enemy_list = []
        for (i, c) in enumerate(enemies):
            if c == "1":
                m = MonsterObject.get(getattr(self, "monster%s" % i))
                enemy_list.append(m)
        return enemy_list


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
            for attr in LEVEL_STATS:
                setattr(self, attr, getattr(self, attr) + getattr(g, attr))

        if self.level == 1:
            self.xp = 0
        else:
            self.xp = LevelUpXPObject.get(self.level-2).xp


class ItemObject(TableObject):
    flag = "i"
    flag_description = "item stats and equippability"
    banned_indexes = ([0, 1, 2, 3, 4, 0x23, 0x24, 0x47, 0x48, 0x49, 0x8b,
                       0x95, 0xa0] + range(0xb1, 0x100))

    @property
    def name(self):
        return ItemNameObject.get(self.index).name

    @property
    def price(self):
        return PriceObject.get(self.index).price

    @property
    def is_frog_coin_item(self):
        for p in ShopObject.every:
            if self.index in p.items:
                return p.uses_frog_coins
        return None

    @property
    def banned(self):
        return self.index in self.banned_indexes

    @property
    def is_weapon(self):
        return (self.variance and (self.useable_itemtype & 0x3) == 0
                and not self.banned)

    @property
    def is_armor(self):
        return (self.useable_itemtype & 0x3) == 1 and not self.banned

    @property
    def is_accessory(self):
        return (self.useable_itemtype & 0x3) == 2 and not self.banned

    @property
    def is_equipment(self):
        return self.is_weapon or self.is_armor or self.is_accessory

    @property
    def primary_stats(self):
        if self.is_weapon:
            return ["attack"]
        elif self.is_armor:
            return ["defense", "magic_defense"]
        return EQUIP_STATS

    @property
    def stat_point_value(self):
        score = 0
        for attr in EQUIP_STATS:
            value = getattr(self, attr)
            if value & 0x80:
                score += (value - 256)
            elif attr in self.primary_stats:
                score += value
            else:
                score += (2*value)
        return score

    @property
    def is_consumable(self):
        return self.useable_battle or self.useable_field

    @property
    def is_key(self):
        return not (self.is_equipment or self.is_consumable or self.banned)

    @property
    def useable_battle(self):
        return self.useable_itemtype & 0x08

    @property
    def useable_field(self):
        return self.useable_itemtype & 0x10

    @property
    def reuseable(self):
        return self.useable_itemtype & 0x20

    def mutate(self):
        self.mutate_equipment()

    def mutate_equipment(self):
        if not self.is_equipment:
            return
        score = self.stat_point_value
        num_up = bin(random.randint(1, 31)).count('1')
        num_down = bin(random.randint(0, 31)).count('1')
        while True:
            if random.choice([True, False, False]):
                ups = [attr for attr in EQUIP_STATS
                       if 1 <= getattr(self, attr) <= 127]
                if ups:
                    break
            ups = random.sample(EQUIP_STATS, num_up)
            if set(ups) & set(self.primary_stats):
                break
        ups = dict([(u, 0) for u in ups])
        if random.choice([True, False, False]):
            downs = [attr for attr in EQUIP_STATS
                   if getattr(self, attr) >= 128]
        else:
            downs = random.sample(EQUIP_STATS, num_down)
        downs = dict([(d, 0) for d in downs if d not in ups])
        if downs:
            if score != 0:
                downpoints = random.randint(0, random.randint(0, score))
            else:
                downpoints = random.randint(0, random.randint(0, random.randint(0, 100)))
            while downpoints > 0:
                attr = random.choice(downs.keys())
                downs[attr] += 1
                downpoints -= 1
                score += 1
        while score > 0:
            attr = random.choice(ups.keys())
            ups[attr] += 1
            if attr in self.primary_stats:
                score -= 1
            else:
                score -= 2

        for attr in EQUIP_STATS:
            setattr(self, attr, 0)

        for attr in ups:
            setattr(self, attr, min(mutate_normal(
                ups[attr], minimum=1, maximum=127), 127))

        for attr in downs:
            value = min(mutate_normal(
                downs[attr], minimum=1, maximum=127), 127)
            if value:
                setattr(self, attr, 256 - value)

        self.equippable &= 0xE0
        self.equippable |= random.randint(1, 31)

    def cleanup(self):
        if self.index in [0x5, 0x23]:
            # mario must equip tutorial hammer
            self.set_bit("mario", True)


class ItemNameObject(TableObject): pass
class PriceObject(TableObject): pass


class LevelUpXPObject(TableObject):
    flag = "c"

    @classmethod
    def full_randomize(cls):
        if hasattr(cls, "after_order"):
            for cls2 in cls.after_order:
                if not (hasattr(cls2, "randomized") and cls2.randomized):
                    raise Exception("Randomize order violated.")
        cls.randomized = True
        xps = sorted([mutate_normal(l.xp, minimum=1, maximum=65535)
                      for l in cls.every])
        prev = 0
        for l, xp in zip(cls.every, xps):
            while xp <= prev:
                xp += 1
            l.xp = xp
            prev = xp


class StatGrowthObject(StatObject, TableObject):
    flag = "c"

    @classmethod
    def full_randomize(cls):
        if hasattr(cls, "after_order"):
            for cls2 in cls.after_order:
                if not (hasattr(cls2, "randomized") and cls2.randomized):
                    raise Exception("Randomize order violated.")
        cls.randomized = True
        curves = defaultdict(list)
        for character_index in range(5):
            c = CharacterObject.get(character_index)
            for attr in LEVEL_STATS:
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

        for attr in LEVEL_STATS:
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
        for attr in LEVEL_STATS:
            self.set_stat(attr, mutate_normal(
                getattr(self, attr), minimum=0, maximum=0xf))


class SpellObject(TableObject):
    flag = "s"
    mutate_attributes = {
            "fp": (1, 99),
            "power": None,
            "hitrate": (1, 100),
            }

    @property
    def name(self):
        return SpellNameObject.get(self.index).name

    @property
    def animation_pointer(self):
        return AllyAnimPTRObject.get(self.index)

    def set_name(self, name):
        SpellNameObject.get(self.index).name = name


class SpellNameObject(TableObject): pass
class AllyAnimPTRObject(TableObject): pass
class EnemAnimPTRObject(TableObject):
    @classmethod
    def get_full_index(cls, index):
        return cls.get(index - 0x40)


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
        supplemental = [0xFF] * 3
        spells = spells + supplemental
        charspells = defaultdict(list)
        while spells:
            valid = [i for i in range(5) if len(charspells[i]) < 6]
            chosen = random.choice(valid)
            spell = spells.pop(0)
            if spell == 0xFF:
                valid = [s for s in range(0x1b) if s not in charspells[i]]
                spell = random.choice(valid)
            charspells[chosen].append(spell)
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


class ShopObject(TableObject):
    @property
    def uses_frog_coins(self):
        return self.get_bit("frog_coins") or self.get_bit("frog_coins_limited")

    @property
    def is_juice_bar(self):
        return 0x9 <= self.index <= 0xC

    def __repr__(self):
        s = "%x " % self.index
        s += "FROG COINS\n" if self.uses_frog_coins else "COINS\n"
        for i in self.items:
            if i == 0xFF:
                continue
            s += "%s\n" % ItemObject.get(i).name.strip()
        return s.strip()


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
