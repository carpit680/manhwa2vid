# Script comparison — reference vs generated

Reference: `reference/frozen_player/ch1-2_gold_script.md` · Candidate: `projects/return-of-the-frozen-player-ch1-2/script.json`

## Content (does it tell the same story?)

- fact_coverage: **0.45** of 357 salient reference terms
- order_tau: **0.33** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): cavern, lone, swordsman, steps, etched, snowflakes, brands, encountered, descends, crowned, gown, feels, abandoning, doesn't, take, bait, aren't, kind, easily, glowing, blade, killing, he'll, ignorant, works

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 25 | 18 |
| words | 1048 | 984 |
| avg_sentence_words | 13.1 | 16.1 |
| caption_markers_per_100w | 0.0 | 0.0 |
| speech_verbs_per_100w | 1.24 | 1.63 |
| connectives_per_100w | 2.39 | 2.24 |
| max_consecutive_pronoun_starts | 5 | 2 |
| pronoun_start_fraction | 0.2 | 0.25 |

## Side by side

### Beat 1

**reference** 

Deep inside an ice cavern, a lone swordsman in black steps onto a frozen floor
etched with snowflakes. A system message brands the moment: he has encountered
the Frost Queen. She descends from her throne of ice, a crowned silhouette in a
gown of frost, and asks how it feels to stand here after abandoning his
comrades to die.

**candidate** `p0001_02, p0001_03, p0001_04, p0001_05, p0001_06, p0001_07, p0002_01, p0002_02, p0002_03, p0002_04, p0002_05, p0002_06`

Twenty-five years ago, Seo Jun-Ho confronts the Frost Queen, the ruler of the final dungeon in Antarctica, in her Nest's throne room, where he draws his weapon and vows to slay her.

### Beat 2

**reference** 

He doesn't take the bait. His friends aren't the kind to die that easily, he
says, drawing a glowing blade — if killing her ends this, he'll do it here.
She only laughs, calling him ignorant of how this world really works. He tells
her to be quiet. He has no time to waste.

**candidate** `p0002_09, p0002_10, p0002_11, p0003_01, p0003_02, p0003_03, p0003_04, p0003_05, p0003_06, p0004_01, p0004_02, p0004_03, p0004_04, p0004_05`

An intense battle erupts as Jun-Ho clashes with the Frost Queen, exchanging rapid blows and shattering the frozen ground.

### Beat 3

**reference** 

The queen conjures a sword of pure ice, and they collide in midair. The duel
tears the throne room apart — ice shards, black flashes, magic detonating off
the walls. She hurls a point-blank blast; he slips past it by a breath.

**candidate** `p0005_01, p0005_02, p0005_04, p0005_06, p0005_08, p0005_10`

Frost Queen smiles as she begins to dissipate into light, admitting that the battle was fun. Jun-Ho looks down coldly and replies that he cannot say the same. Even as a brilliant flash of energy erupts, he delivers one final strike to end the fight. Thick layers of ice suddenly crawl up his body while the monster vanishes completely. He wonders what is happening as the frost rapidly encases his face and limbs.

### Beat 4

**reference** 

One final exchange, and the hall falls silent. The Frost Queen kneels, beaten.
She admits she had fun. He can't say the same. But before his blade can finish
it, her body begins to glow — and the ice turns on him, crawling up his arms.

**candidate** `p0005_11, p0005_12, p0005_14, p0006_02, p0006_03, p0006_04, p0006_05, p0006_06, p0006_07, p0006_08, p0006_09`

A system prompt explains that he must enter hibernation to absorb the nucleus. A flashback to twenty-five years ago reveals Khali, the team's tattooed vanguard who yielded his spot to Jun-Ho, venting his frustration because only one person can advance. Skaya, the party's white-haired healer who stayed behind during the Nest raid, nominates Seo Jun-Ho to go, and the marksman, the team's cowboy-hat-wearing marksman, agrees.

### Beat 5

**reference** 

A system message explains the price: he is absorbing the Frost Queen's power,
and his body will hibernate until her nucleus is fully absorbed. Frost swallows
him whole, sword still in hand.

**candidate** `p0007_02, p0007_03, p0007_04, p0007_05, p0007_06, p0007_07, p0007_08, p0007_09, p0007_10, p0007_11, p0008_02, p0008_03`

Khali concedes to the choice, prompting the swordswoman, the team's short-haired swordswoman, to express her full agreement. Although Jun-Ho asks if they will regret their decision, his comrades reassure him of their absolute trust.

### Beat 6

**reference** 

Seventy-six hours earlier, in Antarctica, five hunters stand at the mouth of
humanity's final dungeon — the Frost Queen's Nest. The rule carved into it is
simple and cruel: only one person may climb the stairs.

**candidate** `p0008_04, p0008_05, p0008_06, p0008_07, p0008_08, p0008_09, p0008_10, p0008_11, p0008_12, p0008_13, p0009_01, p0009_02`

Skaya smiles, encouraging him not to let their sacrifices be in vain. Twenty-five years later, a presenter in a modern auditorium lectures an audience about the Frost Queen's terrifying abilities, while a schoolboy asks about Jun-Ho and his Nest Attack Team.

### Beat 7

**reference** 

Khali, a mountain of a man in tattoos, punches the ice wall — sending one
person up alone means telling the other four to die. Skaya, the party's
white-haired healer, calms him: time is short, and she believes Specter should
be the one to go.

**candidate** `p0009_03, p0009_04, p0009_05, p0009_06, p0009_07, p0009_08, p0009_09, p0009_10`

Bright stage lights hum as the story shifts to a modern museum auditorium. The presenter snaps his fingers to unveil five massive blocks of ancient ice. He tells the audience that these legendary figures are known as the Five Heroes. Spectators gaze at the frozen forms of Khali and Skaya held in permanent slumber. Deep inside the monument, the hand of Jun-Ho remains perfectly preserved within the frost. A schoolboy points toward the stage and shouts that the ice statue just... The presenter dismisses the child as incorrect before leading the crowd away. Tiny shards of ice begin to splinter from the body

### Beat 8

**reference** 

The cowboy-hatted marksman agrees — against an ice monster, everyone but
Specter fights at a disadvantage. Khali concedes there's no one quite like
him. The swordswoman closes it: it's best if Specter goes.

**candidate** `p0010_03, p0010_04, p0010_05, p0010_06, p0010_08, p0011_01`

The presenter turns back toward the statues in confusion as the central monument begins to crack. While they shout that there is no way this is happening, the ice violently shatters into jagged shards. He bursts from his prison and collapses onto the museum floor, his body trembling uncontrollably. Shivering in the open air, he mutters that he is freezing.

### Beat 9

**reference** 

Specter asks if they're sure they won't regret this. The marksman shrugs —
they might, if he loses and their deaths mean nothing. But they trust him.
Skaya smiles and says she knows he won't let their deaths be in vain.

**candidate** `p0011_02, p0011_03, p0011_04, p0011_05, p0011_06, p0012_01, p0012_02, p0012_03, p0012_04, p0012_07, p0012_09`

While the crowd panics, system notifications confirm that Jun-Ho has absorbed the Frost Queen's nucleus, gaining the Frost (EX) skill. Later in a hospital room, he reads news of his twenty-five-year slumber and laments his weakened hands just as the medical staff announces the Player Association President is arriving.

### Beat 10

**reference** 

All he can manage is a quiet "you guys." Alone on the stairs, their voices at
his back — if it's you, you can do this — he whispers an apology and climbs.

**candidate** `p0012_10, p0012_12, p0012_14, p0013_01, p0013_02, p0013_03, p0013_04, p0013_05, p0013_07, p0013_08, p0013_12, p0013_15`

Jun-Ho stares down at his own open hand as the chief doctor watches him. He admits that very few people would ever call him their true friend. Still, he thanks the doctor for delivering the honest news. Memories of his fallen comrades suddenly flash before his eyes. He envisions Skaya standing tall. Beside her stands Khali. The group also includes the marksman and the swordswoman. Looking toward the bright sky, he whispers that his old friends achieved their dream. They successfully created the peaceful, safe world they always wanted. He walks over to the massive window to survey the bustling modern city below. Countless soaring skyscrapers stretch out across the vast horizon. He realizes his grueling battles finally secured this lasting peace. Preparing for the next hunt, he raises his black face mask. He gazes down thoughtfully as he braces himself for an unfamiliar future.

### Beat 11

**reference** 

Twenty-five years later, under a clear Seoul sky, a lecture hall is learning
about the monsters humanity never beat. The presenter recounts how the Frost
Queen froze the Pacific with a wave of her hand — and how the Nest Attack
Team, the Five Heroes, went to Antarctica to stop her.

**candidate** `p0013_16, p0013_17, p0013_18, p0014_01, p0014_03, p0014_04, p0014_05, p0014_07, p0014_08, p0014_09, p0014_10, p0014_11`

He looks down at the black mask that once defined his legendary identity. The chief doctor freezes and whispers that he is Specter, the era's greatest hunter. He asks why the hero would reveal his face now while the staff trembles in shock. He just smiles warmly at their confusion until the hospital room door swings open. Shim Deok-gu, the Player Association president and his old friend, enters the room with his bodyguards.

### Beat 12

**reference** 

On stage stands their memorial: five figures sculpted in ice. Then a boy in
the audience starts shouting — the statue just moved. The presenter laughs it
off, until the cracking starts behind her.

**candidate** `p0015_01, p0015_02, p0015_03, p0015_04, p0015_06, p0015_07, p0015_08, p0016_05, p0016_06, p0016_07`

Jun-Ho bursts out laughing at Shim Deok-gu's baldness, but their reunion quickly turns serious as they sit down to talk. The president recounts how humanity rejoiced and safe zones appeared worldwide immediately after the Frost Queen was defeated.

### Beat 13

**reference** 

The ice explodes. A young man collapses out of the shards, steaming with
cold, and a system message finally updates: absorption one hundred percent.
Congratulations. The Frost Queen's nucleus is his, and a new skill with it —
Frost, EX rank.

**candidate** `p0016_08, p0016_09, p0016_10, p0016_11, p0016_13, p0016_16, p0016_18, p0016_19, p0016_20, p0017_02, p0017_03, p0017_04`

The global celebration was short-lived, as a massive Dimensional Elevator suddenly appeared in the Pacific Ocean. World leaders quickly organized an expedition to the second floor, which yielded advanced magic, technology, and resources for the players, including his silhouetted team.

### Beat 14

**reference** 

His first words in twenty-five years: "Co... cold." As staff rush the stage,
the weakest whisper in the hall belongs to the strongest player alive. The
Frozen Player has returned.

**candidate** `p0017_05, p0017_06, p0017_07, p0017_10, p0018_01, p0018_02, p0018_03, p0018_04, p0018_06, p0018_09, p0018_12, p0018_13, p0018_14, p0018_16`

He asks about their current progress, expecting them to be far higher than the second floor after twenty-five years. He collapses back onto his hospital bed in utter disbelief when Shim Deok-gu admits that humanity's progress has completely stalled.

### Beat 15

**reference** 

The news breaks worldwide: the legend is awake, the Specter who felled the
Frost Queen, back after twenty-five years of cryogenic sleep. The man himself
sits in a hospital bed scrolling headlines, muttering that it's really been
that long. He can barely close his shaking hand into a fist.

**candidate** `p0019_01, p0019_02, p0019_03, p0019_04, p0019_05, p0019_09, p0019_10, p0019_11, p0019_12, p0019_13`

Jun-Ho sits up in a fury, demanding to know how they only cleared the second floor. Shim Deok-gu explains that the third floor is a volcanic region where further exploration is blocked by a sea of lava that can only be cooled down by the missing Frost Queen's nucleus.

### Beat 16

**reference** 

A doctor announces the president of the Player Association is on his way.
Jun-Ho isn't interested in strangers — but this one, they say, is an old
friend. He takes off his mask to the staff's disbelief and waits.

**candidate** `p0020_01, p0020_02, p0020_03, p0020_04, p0020_05, p0020_06, p0020_07, p0020_08, p0020_10, p0020_11, p0020_12, p0020_14`

After Shim Deok-gu laments that searching the Nest for the nucleus was useless, Seo Jun-Ho silently realizes he absorbed it himself. He pats his old friend on the shoulder to comfort him, moving the president to tears of gratitude.

### Beat 17

**reference** 

The president arrives flanked by suits, and one look is enough. Deok-gu — the
same voice, minus the hair. Jun-Ho bursts out laughing: he called that
M-pattern baldness twenty-five years ago. So much for a touching reunion.

**candidate** `p0020_15, p0021_01, p0021_12, p0021_13, p0022_01, p0022_02, p0022_03, p0022_04, p0022_05, p0022_06, p0022_07`

To avoid the reporters waiting outside the hospital, Seo Jun-Ho secretly heads to the museum's secure basement vault. After passing authentication, he enters a cold hall and sits before the frozen statues of his four teammates, apologizing for being late.

### Beat 18

**reference** 

Alone, Deok-gu lays out the missing years. When the Frost Queen fell, every
player heard the same message, and the world wept with joy — for about a
minute. Then a dimensional elevator rose in the Pacific: the second floor was
open, ten floors in all. Stay strong until the final floor.

**candidate** `p0023_01, p0023_02, p0023_04, p0023_05, p0023_06, p0023_07, p0023_08, p0023_09, p0023_10, p0023_12, p0023_13, p0024_01, p0024_03`

Remembering their happy times, Jun-Ho pours alcohol into paper cups to share a drink with his frozen teammates. However, when he touches the swordswoman to wipe away the dust, a system notification alerts him that his magic stats are too low to break the seal.

### Beat 19

**reference** 

Jun-Ho does the math out loud — five years for one floor, so in twenty-five
they should be on the seventh. Deok-gu can barely say it: humanity has
cleared one. The third floor is a sea of lava, and the only thing that can
cool it is an altar that demands the Frost Queen's nucleus.

**candidate** 

(no candidate beat)

### Beat 20

**reference** 

The nucleus they searched the Nest decades for. Jun-Ho goes very quiet,
because he knows exactly where it is — he absorbed it. With the straightest
face he can manage, he declares they were simply unlucky, and everyone should
be understanding about honest mistakes. Deok-gu is not.

**candidate** 

(no candidate beat)

### Beat 21

**reference** 

That evening, Jun-Ho asks where his team ended up. The Seoul History Museum —
though Deok-gu warns the streets below are crawling with reporters. Which is
why, hours later, a hooded figure badges through a service door instead.

**candidate** 

(no candidate beat)

### Beat 22

**reference** 

He walks past a dragon's skeleton — annoyed they put that thing on display —
into a hall kept cold on purpose. There they are: his four friends, frozen
mid-stride, exhibited like trophies.

**candidate** 

(no candidate beat)

### Beat 23

**reference** 

He sits down in front of them and apologizes for being late. Four paper cups,
one bottle shared with the dead — the world is a better place now, he tells
them; the peace they dreamed of held. So now... rest.

**candidate** 

(no candidate beat)

### Beat 24

**reference** 

He can't finish the sentence. Brushing the dust from Skaya's ice, he mutters
that the alcohol tastes sweet. Then a system message cuts through the grief:
Frost EX confirmed — insufficient magic — seal removal failed.

**candidate** 

(no candidate beat)

### Beat 25

**reference** 

Seal. Not tomb. The message spells it out: with the Frost skill, the ice
holding his friends can be undone. They were never dead — and now the
strongest player in history, reduced to a shaking fist, has a reason to start
over. What?!

**candidate** 

(no candidate beat)
