# Script comparison — reference vs generated

Reference: `reference/frozen_player/ch1-2_gold_script.md` · Candidate: `projects/return-of-the-frozen-player-ch1-2/script.json`

## Content (does it tell the same story?)

- fact_coverage: **0.38** of 357 salient reference terms
- order_tau: **0.33** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): deep, cavern, swordsman, steps, etched, snowflakes, brands, encountered, descends, crowned, silhouette, gown, feels, abandoning, doesn't, take, bait, aren't, kind, easily, drawing, he'll, ignorant, works, waste

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 25 | 28 |
| words | 1048 | 806 |
| avg_sentence_words | 13.1 | 14.4 |
| caption_markers_per_100w | 0.0 | 0.0 |
| speech_verbs_per_100w | 1.24 | 0.99 |
| connectives_per_100w | 2.39 | 2.85 |
| max_consecutive_pronoun_starts | 5 | 2 |
| pronoun_start_fraction | 0.2 | 0.32 |

## Side by side

### Beat 1

**reference** 

Deep inside an ice cavern, a lone swordsman in black steps onto a frozen floor
etched with snowflakes. A system message brands the moment: he has encountered
the Frost Queen. She descends from her throne of ice, a crowned silhouette in a
gown of frost, and asks how it feels to stand here after abandoning his
comrades to die.

**candidate** `p0001_02, p0001_03, p0001_04, p0001_05, p0001_06, p0001_07, p0002_01, p0002_02, p0002_03, p0002_04, p0002_05, p0002_06`

Inside the Frost Queen's Nest, Seo Jun-Ho faces the legendary monster. She mocks his decision to leave his comrades behind, but he ignores her taunts. Gripping his blade, he admits he has no time to fool around and prepares to kill her tonight.

### Beat 2

**reference** 

He doesn't take the bait. His friends aren't the kind to die that easily, he
says, drawing a glowing blade — if killing her ends this, he'll do it here.
She only laughs, calling him ignorant of how this world really works. He tells
her to be quiet. He has no time to waste.

**candidate** `p0002_09, p0002_10, p0002_11, p0003_01, p0003_02, p0003_03`

He launches himself across the ice, meeting the queen in a high-speed clash. Their blades spark as they trade blows through the air. The throne room rumbles with magical energy until a massive burst of frost pushes the legendary hero backward.

### Beat 3

**reference** 

The queen conjures a sword of pure ice, and they collide in midair. The duel
tears the throne room apart — ice shards, black flashes, magic detonating off
the walls. She hurls a point-blank blast; he slips past it by a breath.

**candidate** `p0003_04, p0003_05, p0003_06, p0004_01, p0004_02, p0004_03, p0004_04, p0004_05`

A violent explosion erupts as the Frost Queen charges her final attack. Jun-Ho survives the impact, landing in a low crouch amidst the flying shards. He rises through the swirling aura to deliver the killing strike that brings the monster down.

### Beat 4

**reference** 

One final exchange, and the hall falls silent. The Frost Queen kneels, beaten.
She admits she had fun. He can't say the same. But before his blade can finish
it, her body begins to glow — and the ice turns on him, crawling up his arms.

**candidate** `p0005_01, p0005_02, p0005_04, p0005_06, p0005_08, p0005_10`

A flash of white and purple energy erupts as Jun-Ho strikes the Frost Queen, but creeping ice suddenly consumes his body.

### Beat 5

**reference** 

A system message explains the price: he is absorbing the Frost Queen's power,
and his body will hibernate until her nucleus is fully absorbed. Frost swallows
him whole, sword still in hand.

**candidate** `p0005_11, p0005_12, p0005_14, p0006_02, p0006_03, p0006_04, p0006_05, p0006_06, p0006_07, p0006_08, p0006_09`

Twenty-five years ago in Antarctica, a system prompt warned the party that only one person could enter the final dungeon. Khali, a member of the original five heroes, screamed in fury and punched the ice. Skaya tried to calm him and suggested they decide quickly.

### Beat 6

**reference** 

Seventy-six hours earlier, in Antarctica, five hunters stand at the mouth of
humanity's final dungeon — the Frost Queen's Nest. The rule carved into it is
simple and cruel: only one person may climb the stairs.

**candidate** `p0007_02, p0007_03, p0007_04, p0007_05, p0007_06, p0007_07`

Khali clenches his jaw in frustration, admitting he hates that he cannot be the one to go. He lets out a sigh and extends a hand in surrender, conceding that no one truly compares to Specter.

### Beat 7

**reference** 

Khali, a mountain of a man in tattoos, punches the ice wall — sending one
person up alone means telling the other four to die. Skaya, the party's
white-haired healer, calms him: time is short, and she believes Specter should
be the one to go.

**candidate** `p0007_08, p0007_09, p0007_10, p0007_11, p0008_02, p0008_03`

Jun-Ho asks his comrades if they will regret their decision. The Marksman replies that they only regret dying meaninglessly if he loses to the Frost Queen, but they trust him. He stares forward silently.

### Beat 8

**reference** 

The cowboy-hatted marksman agrees — against an ice monster, everyone but
Specter fights at a disadvantage. Khali concedes there's no one quite like
him. The swordswoman closes it: it's best if Specter goes.

**candidate** `p0008_04, p0008_05, p0008_06, p0008_07, p0008_08, p0008_09`

Skaya smiles warmly and says she knows Jun-Ho will not let their deaths be in vain. Later, his teammates stand together in a somber memory, apologizing while insisting he can succeed.

### Beat 9

**reference** 

Specter asks if they're sure they won't regret this. The marksman shrugs —
they might, if he loses and their deaths mean nothing. But they trust him.
Skaya smiles and says she knows he won't let their deaths be in vain.

**candidate** `p0008_10, p0008_11, p0008_12, p0008_13, p0009_01, p0009_02, p0009_03, p0009_04, p0009_05, p0009_06`

Twenty-five years later, a presenter in a black suit addresses a large crowd gathered inside a modern auditorium. He explains how humanity once despaired when the Frost Queen froze the Pacific Ocean with a wave of her hand.

### Beat 10

**reference** 

All he can manage is a quiet "you guys." Alone on the stairs, their voices at
his back — if it's you, you can do this — he whispers an apology and climbs.

**candidate** `p0009_07, p0009_08, p0009_09, p0009_10, p0010_03, p0010_04`

A schoolboy points out that the ice statue is moving, but the presenter dismisses him just before him violently shatters his frozen prison.

### Beat 11

**reference** 

Twenty-five years later, under a clear Seoul sky, a lecture hall is learning
about the monsters humanity never beat. The presenter recounts how the Frost
Queen froze the Pacific with a wave of her hand — and how the Nest Attack
Team, the Five Heroes, went to Antarctica to stop her.

**candidate** `p0010_05, p0010_06, p0010_08, p0011_01, p0011_02, p0011_03`

Jun-Ho collapses onto the floor, shivering violently. A system notification confirms he has fully absorbed the nucleus, granting him the skill Frost.

### Beat 12

**reference** 

On stage stands their memorial: five figures sculpted in ice. Then a boy in
the audience starts shouting — the statue just moved. The presenter laughs it
off, until the cracking starts behind her.

**candidate** `p0011_04, p0011_05, p0011_06, p0012_01, p0012_02, p0012_03`

He stares at the news screens in shock, realizing twenty-five years have passed and his body is now too weak to even make a fist.

### Beat 13

**reference** 

The ice explodes. A young man collapses out of the shards, steaming with
cold, and a system message finally updates: absorption one hundred percent.
Congratulations. The Frost Queen's nucleus is his, and a new skill with it —
Frost, EX rank.

**candidate** `p0012_04, p0012_07, p0012_09, p0012_10, p0012_12, p0012_14`

He stares at his trembling hands as the medical staff enters, announcing that the Association president is on his way. He smiles, realizing only a true friend would rush to his side.

### Beat 14

**reference** 

His first words in twenty-five years: "Co... cold." As staff rush the stage,
the weakest whisper in the hall belongs to the strongest player alive. The
Frozen Player has returned.

**candidate** `p0013_01, p0013_02, p0013_03, p0013_04, p0013_05, p0013_07`

Looking out at the soaring city skyline, Jun-Ho reflects that this peaceful world is exactly what his fallen comrades wished for.

### Beat 15

**reference** 

The news breaks worldwide: the legend is awake, the Specter who felled the
Frost Queen, back after twenty-five years of cryogenic sleep. The man himself
sits in a hospital bed scrolling headlines, muttering that it's really been
that long. He can barely close his shaking hand into a fist.

**candidate** `p0013_08, p0013_12, p0013_15, p0013_16, p0013_17, p0013_18`

He looks at his old black mask. He stands completely still, holding the mask in his hand.

### Beat 16

**reference** 

A doctor announces the president of the Player Association is on his way.
Jun-Ho isn't interested in strangers — but this one, they say, is an old
friend. He takes off his mask to the staff's disbelief and waits.

**candidate** `p0014_01, p0014_03, p0014_04, p0014_05, p0014_07, p0014_08`

Deok-gu, Jun-Ho’s old friend and the current Player Association president enters with his bodyguards. He requests privacy, so the staff departs.

### Beat 17

**reference** 

The president arrives flanked by suits, and one look is enough. Deok-gu — the
same voice, minus the hair. Jun-Ho bursts out laughing: he called that
M-pattern baldness twenty-five years ago. So much for a touching reunion.

**candidate** `p0014_09, p0014_10, p0014_11, p0015_01, p0015_02, p0015_03`

But Jun-Ho laughs and points at Deok-gu, teasing his severe M-pattern baldness instead of continuing their touching reunion.

### Beat 18

**reference** 

Alone, Deok-gu lays out the missing years. When the Frost Queen fell, every
player heard the same message, and the world wept with joy — for about a
minute. Then a dimensional elevator rose in the Pacific: the second floor was
open, ten floors in all. Stay strong until the final floor.

**candidate** `p0015_04, p0015_06, p0015_07, p0015_08, p0016_05, p0016_06`

Jun-Ho shifts the conversation to ask for an update. Deok-gu looks down grimly, recalling how players heard the system message.

### Beat 19

**reference** 

Jun-Ho does the math out loud — five years for one floor, so in twenty-five
they should be on the seventh. Deok-gu can barely say it: humanity has
cleared one. The third floor is a sea of lava, and the only thing that can
cool it is an altar that demands the Frost Queen's nucleus.

**candidate** `p0016_07, p0016_08, p0016_09, p0016_10, p0016_11, p0016_13, p0016_16`

A massive crowd of people celebrate in the city streets, cheering and crying tears of joy. But the world does not let this celebration last for even a minute. A sudden chiming sound cuts through the air, and a glowing system message appears.

### Beat 20

**reference** 

The nucleus they searched the Nest decades for. Jun-Ho goes very quiet,
because he knows exactly where it is — he absorbed it. With the straightest
face he can manage, he declares they were simply unlucky, and everyone should
be understanding about honest mistakes. Deok-gu is not.

**candidate** `p0016_18, p0016_19, p0016_20, p0017_02, p0017_03, p0017_04`

A global meeting convenes to address the ten-floor tower, and an expedition squad soon departs for the newly opened second floor.

### Beat 21

**reference** 

That evening, Jun-Ho asks where his team ended up. The Seoul History Museum —
though Deok-gu warns the streets below are crawling with reporters. Which is
why, hours later, a hooded figure badges through a service door instead.

**candidate** `p0017_05, p0017_06, p0017_07, p0017_10, p0018_01, p0018_02`

Deok-gu, Jun-Ho’s old friend and the current Player, explains the elevator has ten floors. He calculates humanity must be on the seventh.

### Beat 22

**reference** 

He walks past a dragon's skeleton — annoyed they put that thing on display —
into a hall kept cold on purpose. There they are: his four friends, frozen
mid-stride, exhibited like trophies.

**candidate** `p0018_03, p0018_04, p0018_06, p0018_09, p0018_12, p0018_13, p0018_14, p0018_16`

Deok-gu, Jun-Ho’s old friend and the current Player Association president, admits humanity is stuck on the second floor. He flops back in disbelief.

### Beat 23

**reference** 

He sits down in front of them and apologizes for being late. Four paper cups,
one bottle shared with the dead — the world is a better place now, he tells
them; the peace they dreamed of held. So now... rest.

**candidate** `p0019_01, p0019_02, p0019_03, p0019_04, p0019_05, p0019_09, p0019_10, p0019_11, p0019_12, p0019_13`

He presses his hands against his forehead, struggling to process that twenty-five years have actually passed. Sitting up as a menacing green aura flares around him, he demands to know why they have only cleared the second floor.

### Beat 24

**reference** 

He can't finish the sentence. Brushing the dust from Skaya's ice, he mutters
that the alcohol tastes sweet. Then a system message cuts through the grief:
Frost EX confirmed — insufficient magic — seal removal failed.

**candidate** `p0020_01, p0020_02, p0020_03, p0020_04, p0020_05, p0020_06`

Deok-gu laments that they searched the Nest countless times. But Jun-Ho sweats, silently knowing he absorbed the core.

### Beat 25

**reference** 

Seal. Not tomb. The message spells it out: with the Frost skill, the ice
holding his friends can be undone. They were never dead — and now the
strongest player in history, reduced to a shaking fist, has a reason to start
over. What?!

**candidate** `p0020_07, p0020_08, p0020_10, p0020_11, p0020_12, p0020_14`

Jun-Ho comforts his weeping friend, Deok-gu saying they were just unlucky and everyone should be understanding. Deok-gu rejoices.

### Beat 26

**reference** 

(no reference beat)

**candidate** `p0020_15, p0021_01, p0021_12, p0021_13, p0022_01, p0022_02, p0022_03, p0022_04, p0022_05, p0022_06, p0022_07`

Deok-gu warns that the hospital is crawling with reporters, so Jun-Ho slips away to a restricted museum gallery. He passes authentication and enters a quiet, cold hall. There, he sits before the frozen statues of his four teammates, apologizing for being late.

### Beat 27

**reference** 

(no reference beat)

**candidate** `p0023_01, p0023_02, p0023_04, p0023_05, p0023_06, p0023_07`

He sits alone on the cold floor, holding a glass to toast them.

### Beat 28

**reference** 

(no reference beat)

**candidate** `p0023_08, p0023_09, p0023_10, p0023_12, p0023_13, p0024_01, p0024_03`

The glowing screen informs him that he can actually melt the ice seals, but his low magic stats cause the attempt to fail. Understanding what he must do, he vows to increase his magic power to free his comrades.
