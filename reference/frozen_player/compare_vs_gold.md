# Script comparison — reference vs generated

Reference: `reference/frozen_player/ch1-2_gold_script.md` · Candidate: `projects/return-of-the-frozen-player-ch1-2/script.json`

## Content (does it tell the same story?)

- fact_coverage: **0.41** of 357 salient reference terms
- order_tau: **0.43** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): inside, cavern, swordsman, steps, etched, snowflakes, brands, descends, crowned, silhouette, gown, feels, abandoning, doesn't, bait, aren't, kind, drawing, glowing, blade, killing, he'll, ignorant, works, conjures

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 25 | 28 |
| words | 1048 | 908 |
| avg_sentence_words | 13.1 | 15.4 |
| caption_markers_per_100w | 0.0 | 0.0 |
| speech_verbs_per_100w | 1.24 | 3.19 |
| connectives_per_100w | 2.39 | 2.64 |
| max_consecutive_pronoun_starts | 5 | 3 |
| pronoun_start_fraction | 0.2 | 0.34 |

## Side by side

### Beat 1

**reference** 

Deep inside an ice cavern, a lone swordsman in black steps onto a frozen floor
etched with snowflakes. A system message brands the moment: he has encountered
the Frost Queen. She descends from her throne of ice, a crowned silhouette in a
gown of frost, and asks how it feels to stand here after abandoning his
comrades to die.

**candidate** `p0001_02, p0001_03, p0001_04, p0001_05, p0001_06, p0001_07, p0002_01, p0002_02, p0002_03`

Seo Jun-Ho, a legendary hero known as Specter faces the Frost Queen, the boss of the final Antarctic dungeon. He stands in her frozen throne room while a system notification confirms their encounter. The monster asks if he regrets leaving his friends. He replies that they won't croak easily. She mocks his ignorance with a laugh.

### Beat 2

**reference** 

He doesn't take the bait. His friends aren't the kind to die that easily, he
says, drawing a glowing blade — if killing her ends this, he'll do it here.
She only laughs, calling him ignorant of how this world really works. He tells
her to be quiet. He has no time to waste.

**candidate** `p0002_04, p0002_05, p0002_06, p0002_09, p0002_10, p0002_11`

Jun-Ho snaps at Frost Queen and promises death as they clash in mid-air.

### Beat 3

**reference** 

The queen conjures a sword of pure ice, and they collide in midair. The duel
tears the throne room apart — ice shards, black flashes, magic detonating off
the walls. She hurls a point-blank blast; he slips past it by a breath.

**candidate** `p0003_01, p0003_02, p0003_03, p0003_04, p0003_05, p0003_06, p0004_01, p0004_02, p0004_03, p0004_04, p0004_05`

Jun-Ho clashes with Frost Queen then stands victorious in her ruined throne room.

### Beat 4

**reference** 

One final exchange, and the hall falls silent. The Frost Queen kneels, beaten.
She admits she had fun. He can't say the same. But before his blade can finish
it, her body begins to glow — and the ice turns on him, crawling up his arms.

**candidate** `p0005_01, p0005_02, p0005_04, p0005_06, p0005_08, p0005_10`

As she dissolves into light, the Frost Queen smiles and admits that their duel was fun. Jun-Ho stares back coldly, replying that he cannot say the same. He delivers one final strike, but his eyes widen when a thick frost crawls up his skin. He cries out as the relentless ice consumes his face.

### Beat 5

**reference** 

A system message explains the price: he is absorbing the Frost Queen's power,
and his body will hibernate until her nucleus is fully absorbed. Frost swallows
him whole, sword still in hand.

**candidate** `p0005_11, p0005_12, p0005_14, p0006_02, p0006_03, p0006_04, p0006_05, p0006_06, p0006_07, p0006_08, p0006_09`

A system prompt alerts Jun-Ho that his body must hibernate to absorb her nucleus, flashing back to when Khali, a heavily tattooed member of the original five heroes, punched an ice wall in frustration. Skaya nominated him to climb the final stairs alone, which was supported by The Marksman due to elemental disadvantages.

### Beat 6

**reference** 

Seventy-six hours earlier, in Antarctica, five hunters stand at the mouth of
humanity's final dungeon — the Frost Queen's Nest. The rule carved into it is
simple and cruel: only one person may climb the stairs.

**candidate** `p0007_02, p0007_03, p0007_04, p0007_05, p0007_06, p0007_07`

Khali clicks his tongue and admits his frustration about staying behind. He eventually concedes because no one else compares to Specter. The Swordswoman observes that his fast agreement confirms their unanimous vote. Khali barks a retort at her jab, yet she remains serious about sending Jun-Ho alone.

### Beat 7

**reference** 

Khali, a mountain of a man in tattoos, punches the ice wall — sending one
person up alone means telling the other four to die. Skaya, the party's
white-haired healer, calms him: time is short, and she believes Specter should
be the one to go.

**candidate** `p0007_08, p0007_09, p0007_10, p0007_11, p0008_02, p0008_03`

He asks if they will regret this, but The Marksman replies they trust him.

### Beat 8

**reference** 

The cowboy-hatted marksman agrees — against an ice monster, everyone but
Specter fights at a disadvantage. Khali concedes there's no one quite like
him. The swordswoman closes it: it's best if Specter goes.

**candidate** `p0008_04, p0008_05, p0008_06, p0008_07, p0008_08, p0008_09`

Skaya, Khali and The Swordswoman tell Jun-Ho that only he can succeed.

### Beat 9

**reference** 

Specter asks if they're sure they won't regret this. The marksman shrugs —
they might, if he loses and their deaths mean nothing. But they trust him.
Skaya smiles and says she knows he won't let their deaths be in vain.

**candidate** `p0008_10, p0008_11, p0008_12, p0008_13, p0009_01, p0009_02, p0009_03, p0009_04, p0009_05, p0009_06`

Twenty-five years later, a presenter in a black suit with black hair explains the legacy of the final dungeon team to an audience, unveiling the ice statues of the five legendary heroes, including the frozen body of Jun-Ho.

### Beat 10

**reference** 

All he can manage is a quiet "you guys." Alone on the stairs, their voices at
his back — if it's you, you can do this — he whispers an apology and climbs.

**candidate** `p0009_07, p0009_08, p0009_09, p0009_10, p0010_03, p0010_04`

Deep within the frozen monument, the hand of Seo Jun-Ho suddenly twitches beneath the surface. A schoolboy points excitedly and says that the ice statue just moved. The presenter, a museum historian, tells him he is wrong while the ice cracks. The casing shatters with a violent boom, forcing him to admit it is impossible.

### Beat 11

**reference** 

Twenty-five years later, under a clear Seoul sky, a lecture hall is learning
about the monsters humanity never beat. The presenter recounts how the Frost
Queen froze the Pacific with a wave of her hand — and how the Nest Attack
Team, the Five Heroes, went to Antarctica to stop her.

**candidate** `p0010_05, p0010_06, p0010_08, p0011_01, p0011_02, p0011_03`

The monument erupts as he bursts through his frozen shell, sending the presenter stumbling back. He collapses and shivers in the open air, thinking that it is incredibly cold. System prompts announce that he has absorbed the queen’s nucleus and gained Frost (EX), a rank representing extraordinary power levels.

### Beat 12

**reference** 

On stage stands their memorial: five figures sculpted in ice. Then a boy in
the audience starts shouting — the statue just moved. The presenter laughs it
off, until the cracking starts behind her.

**candidate** `p0011_04, p0011_05, p0011_06, p0012_01, p0012_02, p0012_03, p0012_04`

Jun-Ho collapses on the shattered floor while the panicked presenter asks what is happening. Holographic news feeds immediately report that the legendary Specter has finally returned after his long slumber. Resting in a quiet hospital bed, he marvels that twenty-five years have actually passed. His fingers tremble as he admits he can barely clench his hands.

### Beat 13

**reference** 

The ice explodes. A young man collapses out of the shards, steaming with
cold, and a system message finally updates: absorption one hundred percent.
Congratulations. The Frost Queen's nucleus is his, and a new skill with it —
Frost, EX rank.

**candidate** `p0012_07, p0012_09, p0012_10, p0012_12, p0012_14, p0013_01, p0013_02, p0013_03, p0013_04, p0013_05, p0013_07`

When a doctor announces the arrival of the association president, he looks out at the sprawling modern skyscrapers, realizing his friends achieved their dream of a peaceful world.

### Beat 14

**reference** 

His first words in twenty-five years: "Co... cold." As staff rush the stage,
the weakest whisper in the hall belongs to the strongest player alive. The
Frozen Player has returned.

**candidate** `p0013_08, p0013_12, p0013_15, p0013_16, p0013_17, p0013_18`

As he holds his mask, the chief doctor gasps, calls him Specter, and asks why he is taking it off.

### Beat 15

**reference** 

The news breaks worldwide: the legend is awake, the Specter who felled the
Frost Queen, back after twenty-five years of cryogenic sleep. The man himself
sits in a hospital bed scrolling headlines, muttering that it's really been
that long. He can barely close his shaking hand into a fist.

**candidate** `p0014_01, p0014_03, p0014_04, p0014_05, p0014_07, p0014_08`

Jun-Ho stares in disbelief as Deok-gu, his old friend and the current President enters and dismisses the bowing doctors.

### Beat 16

**reference** 

A doctor announces the president of the Player Association is on his way.
Jun-Ho isn't interested in strangers — but this one, they say, is an old
friend. He takes off his mask to the staff's disbelief and waits.

**candidate** `p0014_09, p0014_10, p0014_11, p0015_01, p0015_02, p0015_03`

Deok-gu tells his friend that Jun-Ho looks exactly the same as he always did. Recognizing that distinct voice, he laughs and asks how his old companion developed such severe M-pattern baldness. He calls it a touching reunion while Deok-gu rubs his head and mutters that he hasn't changed one bit.

### Beat 17

**reference** 

The president arrives flanked by suits, and one look is enough. Deok-gu — the
same voice, minus the hair. Jun-Ho bursts out laughing: he called that
M-pattern baldness twenty-five years ago. So much for a touching reunion.

**candidate** `p0015_04, p0015_06, p0015_07, p0015_08, p0016_05, p0016_06`

Jun-Ho shifts the topic, and Deok-gu recalls when the system announced their final dungeon victory.

### Beat 18

**reference** 

Alone, Deok-gu lays out the missing years. When the Frost Queen fell, every
player heard the same message, and the world wept with joy — for about a
minute. Then a dimensional elevator rose in the Pacific: the second floor was
open, ten floors in all. Stay strong until the final floor.

**candidate** `p0016_07, p0016_08, p0016_09, p0016_10, p0016_11, p0016_13, p0016_16`

Humanity rejoices, but a sudden system message shatters the peace, declaring a dimensional elevator is installed in the Pacific Ocean.

### Beat 19

**reference** 

Jun-Ho does the math out loud — five years for one floor, so in twenty-five
they should be on the seventh. Deok-gu can barely say it: humanity has
cleared one. The third floor is a sea of lava, and the only thing that can
cool it is an altar that demands the Frost Queen's nucleus.

**candidate** `p0016_18, p0016_19, p0016_20, p0017_02, p0017_03, p0017_04`

As the system opens the Frontier, world leaders meet. He says their expedition to the second floor brings back vast knowledge.

### Beat 20

**reference** 

The nucleus they searched the Nest decades for. Jun-Ho goes very quiet,
because he knows exactly where it is — he absorbed it. With the straightest
face he can manage, he declares they were simply unlucky, and everyone should
be understanding about honest mistakes. Deok-gu is not.

**candidate** `p0017_05, p0017_06, p0017_07, p0017_10, p0018_01, p0018_02`

Jun-Ho asks what came next while Deok-gu describes the Dimensional Elevator, a spire rising from the Pacific. His old friend reveals that the structure contains ten floors in total. He calculates that humanity should have reached the seventh floor by now. He stares past Deok-gu at the ghosts of his team and weighs their accomplishments.

### Beat 21

**reference** 

That evening, Jun-Ho asks where his team ended up. The Seoul History Museum —
though Deok-gu warns the streets below are crawling with reporters. Which is
why, hours later, a hooded figure badges through a service door instead.

**candidate** `p0018_03, p0018_04, p0018_06, p0018_09, p0018_12, p0018_13, p0018_14, p0018_16`

Deok-gu, Jun-Ho's old friend and the current President, says they are only on the second floor, leaving Jun-Ho utterly speechless.

### Beat 22

**reference** 

He walks past a dragon's skeleton — annoyed they put that thing on display —
into a hall kept cold on purpose. There they are: his four friends, frozen
mid-stride, exhibited like trophies.

**candidate** `p0019_01, p0019_02, p0019_03, p0019_04, p0019_05, p0019_09, p0019_10, p0019_11, p0019_12, p0019_13`

He sits up in fury, demanding an explanation, and Deok-gu explains that the third floor is a volcanic wasteland requiring the Frost Queen's nucleus to cool.

### Beat 23

**reference** 

He sits down in front of them and apologizes for being late. Four paper cups,
one bottle shared with the dead — the world is a better place now, he tells
them; the peace they dreamed of held. So now... rest.

**candidate** `p0020_01, p0020_02, p0020_03, p0020_04, p0020_05, p0020_06`

Deok-gu says they searched the nest in vain. Still, Jun-Ho knows that he already absorbed it.

### Beat 24

**reference** 

He can't finish the sentence. Brushing the dust from Skaya's ice, he mutters
that the alcohol tastes sweet. Then a system message cuts through the grief:
Frost EX confirmed — insufficient magic — seal removal failed.

**candidate** `p0020_07, p0020_08, p0020_10, p0020_11, p0020_12, p0020_14`

Jun-Ho rests a hand on his friend’s shoulder and tells Deok-gu they were just unlucky. He says they should be understanding because anyone can make a mistake. Deok-gu cries and gazes up before shouting with a sudden, radiant burst of relief. He smiles serenely while his companion finally lets a heavy burden fall.

### Beat 25

**reference** 

Seal. Not tomb. The message spells it out: with the Frost skill, the ice
holding his friends can be undone. They were never dead — and now the
strongest player in history, reduced to a shaking fist, has a reason to start
over. What?!

**candidate** `p0020_15, p0021_01, p0021_12, p0021_13, p0022_01, p0022_02`

Deok-gu, Jun-Ho's old friend and the current President, tells him of reporters, so he passes authentication to see a dragon skeleton.

### Beat 26

**reference** 

(no reference beat)

**candidate** `p0022_03, p0022_04, p0022_05, p0022_06, p0022_07`

Jun-Ho stands before the grand museum entrance and notes that it must be here. He enters a cold vault where thick mist swirls around Khali, Skaya, and his other frozen teammates. After seeing their ice seals, he slumps to the floor and tells them he is sorry for being late.

### Beat 27

**reference** 

(no reference beat)

**candidate** `p0023_01, p0023_02, p0023_04, p0023_05, p0023_06, p0023_07`

He remembers the peace he won, pours alcohol for his frozen comrades, and sits down to share a quiet drink.

### Beat 28

**reference** 

(no reference beat)

**candidate** `p0023_08, p0023_09, p0023_10, p0023_12, p0023_13, p0024_01, p0024_03`

He touches The Swordswoman but his insufficient magic stats fail to melt her seal.
