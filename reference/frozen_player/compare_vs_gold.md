# Script comparison — reference vs generated

Reference: `reference/frozen_player/ch1-2_gold_script.md` · Candidate: `projects/return-of-the-frozen-player-ch1-2/script.json`

## Content (does it tell the same story?)

- fact_coverage: **0.46** of 357 salient reference terms
- order_tau: **0.4** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): cavern, swordsman, steps, etched, snowflakes, brands, descends, crowned, silhouette, gown, doesn't, bait, aren't, kind, glowing, killing, he'll, works, waste, conjures, sword, collide, midair, duel, apart

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 25 | 28 |
| words | 1048 | 1225 |
| avg_sentence_words | 13.1 | 15.5 |
| caption_markers_per_100w | 0.0 | 0.08 |
| speech_verbs_per_100w | 1.24 | 2.04 |
| connectives_per_100w | 2.39 | 2.29 |
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

**candidate** `p0001_02, p0001_03, p0001_04, p0001_05, p0001_06, p0001_07`

Seo Jun-Ho, stands in the vast throne room of the Frost Queen’s Nest to face the final boss. A system alert confirms his encounter as Frost Queen, the final boss of the Antarctic gate, asks if abandoning comrades feels good. He replies that his team won't fall easily and asks if the nightmare ends once she is dead.

### Beat 2

**reference** 

He doesn't take the bait. His friends aren't the kind to die that easily, he
says, drawing a glowing blade — if killing her ends this, he'll do it here.
She only laughs, calling him ignorant of how this world really works. He tells
her to be quiet. He has no time to waste.

**candidate** `p0002_01, p0002_02, p0002_03, p0002_04, p0002_05, p0002_06`

The Frost Queen sneers and laughs at his statement, calling him ignorant, but he commands her to shut up and readies his dark blade.

### Beat 3

**reference** 

The queen conjures a sword of pure ice, and they collide in midair. The duel
tears the throne room apart — ice shards, black flashes, magic detonating off
the walls. She hurls a point-blank blast; he slips past it by a breath.

**candidate** `p0002_09, p0002_10, p0002_11, p0003_01, p0003_02, p0003_03`

Jun-Ho's boot shatters the frozen floor as he launches into the frigid air. He meets the Frost Queen in a violent collision of dark and light energy. They trade a flurry of lethal strikes across the vast throne room. As sparks fly from their crossing blades, a massive surge of ice energy finally forces him backward.

### Beat 4

**reference** 

One final exchange, and the hall falls silent. The Frost Queen kneels, beaten.
She admits she had fun. He can't say the same. But before his blade can finish
it, her body begins to glow — and the ice turns on him, crawling up his arms.

**candidate** `p0003_04, p0003_05, p0003_06, p0004_01, p0004_02, p0004_03, p0004_04, p0004_05`

The Frost Queen smiles and gathers a blinding sphere of energy in her palm. Jun-Ho gasps in shock as a massive explosion of light and ice shatters the throne room. He lands in a low crouch while shards of the frozen floor rain down around him. Finally, he stands victoriously over his defeated foe in the quiet hall.

### Beat 5

**reference** 

A system message explains the price: he is absorbing the Frost Queen's power,
and his body will hibernate until her nucleus is fully absorbed. Frost swallows
him whole, sword still in hand.

**candidate** `p0005_01, p0005_02, p0005_04, p0005_06, p0005_08, p0005_10, p0005_11`

Frost Queen smiles while fading into light, admitting the battle was fun. Jun-Ho looks on coldly and replies that he cannot say the same. One final strike triggers a blinding explosion, but he gasps as ice suddenly races across his skin. A system alert mandates hibernation, a restorative sleep, to absorb her nucleus.

### Beat 6

**reference** 

Seventy-six hours earlier, in Antarctica, five hunters stand at the mouth of
humanity's final dungeon — the Frost Queen's Nest. The rule carved into it is
simple and cruel: only one person may climb the stairs.

**candidate** `p0005_12, p0005_14, p0006_02, p0006_03, p0006_04, p0006_05, p0006_06, p0006_07, p0006_08, p0006_09`

Twenty-five years ago in Antarctica, Khali, the tattooed giant of the original five-member hero party, and Skaya, the white-haired healer of the original five-member hero party, debated who should go up the stairs.

### Beat 7

**reference** 

Khali, a mountain of a man in tattoos, punches the ice wall — sending one
person up alone means telling the other four to die. Skaya, the party's
white-haired healer, calms him: time is short, and she believes Specter should
be the one to go.

**candidate** `p0007_02, p0007_03, p0007_04, p0007_05, p0007_06, p0007_07`

Khali reluctantly yields to the decision, and Skaya, who believes in their leader's strength, reaffirms that only Specter has the elemental advantage to face the boss.

### Beat 8

**reference** 

The cowboy-hatted marksman agrees — against an ice monster, everyone but
Specter fights at a disadvantage. Khali concedes there's no one quite like
him. The swordswoman closes it: it's best if Specter goes.

**candidate** `p0007_08, p0007_09, p0007_10, p0007_11, p0008_02, p0008_03`

Jun-Ho stands at a distance and faces his four trusted comrades. The marksman smiles alongside Skaya. He replies that they might if their leader loses the final battle and they all die in vain. But they still trust him completely, and Seo Jun-Ho simply looks forward in silence.

### Beat 9

**reference** 

Specter asks if they're sure they won't regret this. The marksman shrugs —
they might, if he loses and their deaths mean nothing. But they trust him.
Skaya smiles and says she knows he won't let their deaths be in vain.

**candidate** `p0008_04, p0008_05, p0008_06, p0008_07, p0008_08, p0008_09`

Skaya smiles warmly and tells Jun-Ho she knows he will not let their deaths be in vain. While the team stands together in absolute faith, she asks for his confirmation. He acknowledges their trust as they insist only he can finish the fight, apologizing for the heavy burden they leave behind.

### Beat 10

**reference** 

All he can manage is a quiet "you guys." Alone on the stairs, their voices at
his back — if it's you, you can do this — he whispers an apology and climbs.

**candidate** `p0008_10, p0008_11, p0008_12, p0008_13, p0009_01, p0009_02, p0009_03, p0009_04, p0009_05, p0009_06`

Twenty-five years later, a museum presenter exhibits the frozen statues of the five heroes to an audience, detailing the terrifying power of the Frost Queen.

### Beat 11

**reference** 

Twenty-five years later, under a clear Seoul sky, a lecture hall is learning
about the monsters humanity never beat. The presenter recounts how the Frost
Queen froze the Pacific with a wave of her hand — and how the Nest Attack
Team, the Five Heroes, went to Antarctica to stop her.

**candidate** `p0009_07, p0009_08, p0009_09, p0009_10, p0010_03, p0010_04`

Thick ice holds the hand of him completely frozen inside the memorial. The schoolboy points toward the stage and says that the frozen statue just moved. Dismissing the claim, the presenter tells the boy that he is incorrect. But small shards of ice suddenly flake off from him. The presenter looks back in confusion just before the ice shatters violently. Terrified by the blast, the presenter says that this is impossible.

### Beat 12

**reference** 

On stage stands their memorial: five figures sculpted in ice. Then a boy in
the audience starts shouting — the statue just moved. The presenter laughs it
off, until the cracking starts behind her.

**candidate** `p0010_05, p0010_06, p0010_08, p0011_01, p0011_02, p0011_03, p0011_04, p0011_05`

He bursts from his icy monument in a violent explosion of flying shards. He crashes to the museum floor, shivering violently as he draws his first freezing breath. Shuddering on the cold ground, he says that it is freezing. Floating system windows announce that he has absorbed the boss's nucleus to unlock a new frost skill.

### Beat 13

**reference** 

The ice explodes. A young man collapses out of the shards, steaming with
cold, and a system message finally updates: absorption one hundred percent.
Congratulations. The Frost Queen's nucleus is his, and a new skill with it —
Frost, EX rank.

**candidate** `p0011_06, p0012_01, p0012_02, p0012_03, p0012_04, p0012_07, p0012_09, p0012_10, p0012_12, p0012_14`

The presenter’s voice fades as he reads news in his hospital room. He mutters in shock that twenty-five years have passed. His hands tremble as he admits he can barely clench a fist. When the chief doctor, the hospital’s lead physician, reports that the Player Association president is arriving, he chuckles, knowing he has few friends.

### Beat 14

**reference** 

His first words in twenty-five years: "Co... cold." As staff rush the stage,
the weakest whisper in the hall belongs to the strongest player alive. The
Frozen Player has returned.

**candidate** `p0013_01, p0013_02, p0013_03, p0013_04, p0013_05, p0013_07`

He looks out the window at the modern skyscrapers of the peaceful world, reflecting on the quiet future his frozen teammates had sacrificed everything to protect.

### Beat 15

**reference** 

The news breaks worldwide: the legend is awake, the Specter who felled the
Frost Queen, back after twenty-five years of cryogenic sleep. The man himself
sits in a hospital bed scrolling headlines, muttering that it's really been
that long. He can barely close his shaking hand into a fist.

**candidate** `p0013_08, p0013_12, p0013_15, p0013_16, p0013_17, p0013_18`

Jun-Ho looks down thoughtfully while gripping his old black face mask. The chief doctor, the hospital’s leading physician, enters and stammers the name Specter in total disbelief. He asks why he would finally reveal his face. The nurse, an attending ward medic, and the young doctor, an assistant physician, stand frozen.

### Beat 16

**reference** 

A doctor announces the president of the Player Association is on his way.
Jun-Ho isn't interested in strangers — but this one, they say, is an old
friend. He takes off his mask to the staff's disbelief and waits.

**candidate** `p0014_01, p0014_03, p0014_04, p0014_05, p0014_07, p0014_08`

Deok-gu, the Player Association president and old friend of Jun-Ho, marches inside with his bodyguards. He asks the flustered medical staff what is wrong as they scramble aside. He stares in shock at the balding man who promises to explain everything. The president requests a private conversation, and the doctors bow before leaving them alone.

### Beat 17

**reference** 

The president arrives flanked by suits, and one look is enough. Deok-gu — the
same voice, minus the hair. Jun-Ho bursts out laughing: he called that
M-pattern baldness twenty-five years ago. So much for a touching reunion.

**candidate** `p0014_09, p0014_10, p0014_11, p0015_01, p0015_02, p0015_03`

Deok-gu reveals severe hair loss. He stands by the hospital bed and says that Jun-Ho looks exactly the same. Recognizing that familiar voice, he gasps in surprise and smiles broadly. But the sentimental moment quickly turns to teasing as he points and laughs. He points and laughs at Deok-gu for having severe M-pattern baldness.

### Beat 18

**reference** 

Alone, Deok-gu lays out the missing years. When the Frost Queen fell, every
player heard the same message, and the world wept with joy — for about a
minute. Then a dimensional elevator rose in the Pacific: the second floor was
open, ten floors in all. Stay strong until the final floor.

**candidate** `p0015_04, p0015_06, p0015_07, p0015_08, p0016_05, p0016_06`

As the two men settle down, they transition to a serious discussion about the aftermath of the final battle, recalling the day safe zones appeared on Earth.

### Beat 19

**reference** 

Jun-Ho does the math out loud — five years for one floor, so in twenty-five
they should be on the seventh. Deok-gu can barely say it: humanity has
cleared one. The third floor is a sea of lava, and the only thing that can
cool it is an altar that demands the Frost Queen's nucleus.

**candidate** `p0016_07, p0016_08, p0016_09, p0016_10, p0016_11, p0016_13, p0016_16`

A massive crowd fills the city streets, cheering and crying tears of joy over the victory. But he knows that the world never lets such pure happiness last for very long. A sudden chime echoes everywhere as the system announces a dimensional elevator is installed in the Pacific Ocean. The stunned audience members gasp in silent shock, demanding to know what is happening above them.

### Beat 20

**reference** 

The nucleus they searched the Nest decades for. Jun-Ho goes very quiet,
because he knows exactly where it is — he absorbed it. With the straightest
face he can manage, he declares they were simply unlucky, and everyone should
be understanding about honest mistakes. Deok-gu is not.

**candidate** `p0016_18, p0016_19, p0016_20, p0017_02, p0017_03, p0017_04`

The system announces that travel to the Frontier, a gateway to higher floors, is now possible. Outraged audience members scream that this is nonsense and the Queen should have been the end. He reflects that leaders eventually organized an expedition squad. This floor provided humanity with magic, technology, and vast knowledge.

### Beat 21

**reference** 

That evening, Jun-Ho asks where his team ended up. The Seoul History Museum —
though Deok-gu warns the streets below are crawling with reporters. Which is
why, hours later, a hooded figure badges through a service door instead.

**candidate** `p0017_05, p0017_06, p0017_07, p0017_10, p0018_01, p0018_02`

However, Deok-gu nervously reveals that they are still stuck on the second floor, causing his legendary friend to collapse back onto his bed in utter disbelief.

### Beat 22

**reference** 

He walks past a dragon's skeleton — annoyed they put that thing on display —
into a hall kept cold on purpose. There they are: his four friends, frozen
mid-stride, exhibited like trophies.

**candidate** `p0018_03, p0018_04, p0018_06, p0018_09, p0018_12, p0018_13, p0018_14, p0018_16`

Demanding a proper explanation, Jun-Ho learns that the third floor is a volcanic region that cannot be explored without the cooling power of the Frost Queen's Nucleus.

### Beat 23

**reference** 

He sits down in front of them and apologizes for being late. Four paper cups,
one bottle shared with the dead — the world is a better place now, he tells
them; the peace they dreamed of held. So now... rest.

**candidate** `p0019_01, p0019_02, p0019_03, p0019_04, p0019_05, p0019_09, p0019_10, p0019_11, p0019_12, p0019_13`

Deok-gu admits they searched the nest countless times in vain, unaware that Jun-Ho had already absorbed the nucleus into his own body during his long slumber.

### Beat 24

**reference** 

He can't finish the sentence. Brushing the dust from Skaya's ice, he mutters
that the alcohol tastes sweet. Then a system message cuts through the grief:
Frost EX confirmed — insufficient magic — seal removal failed.

**candidate** `p0020_01, p0020_02, p0020_03, p0020_04, p0020_05, p0020_06`

Jun-Ho keeps the secret to himself and gently comforts Deok-gu, telling him the players were simply unlucky, which moves the weeping president to tears of joy.

### Beat 25

**reference** 

Seal. Not tomb. The message spells it out: with the Frost skill, the ice
holding his friends can be undone. They were never dead — and now the
strongest player in history, reduced to a shaking fist, has a reason to start
over. What?!

**candidate** `p0020_07, p0020_08, p0020_10, p0020_11, p0020_12, p0020_14, p0020_15, p0021_01, p0021_12, p0021_13`

Jun-Ho tells Deok-gu they were simply unlucky and must be understanding about their past mistakes. Deok-gu replies with a joyful shout through tears while he thinks about how to avoid a future lecture. Warned that reporters are swarming the lobby agrees to slip away toward the museum vault.

### Beat 26

**reference** 

(no reference beat)

**candidate** `p0022_01, p0022_02, p0022_03, p0022_04, p0022_05, p0022_06, p0022_07`

Inside the museum vault, Jun-Ho waits for the system to confirm his identity as he walks deeper into the facility. He passes a massive dragon skeleton and wonders today why the beast is on exhibit. Finding the final door, he enters the freezing mist. He sits before Khali and his frozen comrades to apologize for being late.

### Beat 27

**reference** 

(no reference beat)

**candidate** `p0023_01, p0023_02, p0023_04, p0023_05, p0023_06, p0023_07`

After pouring several cups of alcohol, he raises his own and tells his silent friends to have a drink.

### Beat 28

**reference** 

(no reference beat)

**candidate** `p0023_08, p0023_09, p0023_10, p0023_12, p0023_13, p0024_01, p0024_03`

But a second notification warns him that his magic stats are currently too low. Because of this limitation, the system tells him that he failed to remove the seal. Yet, it still reveals that his unique skill makes unsealing their icy status possible. He gasps in utter shock at this unexpected revelation.
