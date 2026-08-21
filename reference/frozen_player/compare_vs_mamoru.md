# Script comparison — reference vs generated

Reference: `reference/frozen_player/mamoru_ch1-2.txt` · Candidate: `projects/return-of-the-frozen-player-ch1-2/script.json`

## Content (does it tell the same story?)

- fact_coverage: **0.4** of 303 salient reference terms
- order_tau: **0.35** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): answer, 25 years, precise, humanity's, she's, feels, whole, nothing, bro, cuts, fool, forms, giant, blade, pure, answers, simple, i'll, kill, nightmare, collide, midair, trading, blows, goku

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 21 | 28 |
| words | 979 | 908 |
| avg_sentence_words | 11.9 | 15.4 |
| caption_markers_per_100w | 0.0 | 0.0 |
| speech_verbs_per_100w | 1.43 | 3.19 |
| connectives_per_100w | 4.19 | 2.64 |
| max_consecutive_pronoun_starts | 3 | 3 |
| pronoun_start_fraction | 0.2 | 0.34 |

## Side by side

### Beat 1

**reference** 

To answer that, we have to go back 25 years to be precise. Humanity's final dungeon, and standing at the end of it is the Frost Queen, the monster that froze the Pacific Ocean with a snap. She's laughing in his face, asking how it feels to make it this far. After leaving his whole team behind to die, she tells him he understands nothing about this world.

**candidate** `p0001_02, p0001_03, p0001_04, p0001_05, p0001_06, p0001_07, p0002_01, p0002_02, p0002_03`

Seo Jun-Ho, a legendary hero known as Specter faces the Frost Queen, the boss of the final Antarctic dungeon. He stands in her frozen throne room while a system notification confirms their encounter. The monster asks if he regrets leaving his friends. He replies that they won't croak easily. She mocks his ignorance with a laugh.

### Beat 2

**reference** 

But Bro cuts her off, saying he's got no time to fool around. She forms a giant blade of pure ice, and he answers with a simple, "I'll kill you and end this nightmare." The two collide midair, trading blows at Goku's speed. She gathers ice magic in her hand and fires it point blank. He dodges by a hair.

**candidate** `p0002_04, p0002_05, p0002_06, p0002_09, p0002_10, p0002_11`

Jun-Ho snaps at Frost Queen and promises death as they clash in mid-air.

### Beat 3

**reference** 

Then in one final exchange, a black flash cuts through the blue silence. The frost queen is on her knees and the guy is standing behind her. She says it was fun. He says he can't say the same.

**candidate** `p0003_01, p0003_02, p0003_03, p0003_04, p0003_05, p0003_06, p0004_01, p0004_02, p0004_03, p0004_04, p0004_05`

Jun-Ho clashes with Frost Queen then stands victorious in her ruined throne room.

### Beat 4

**reference** 

He moves in to finish it, but the moment she starts to glow, his body starts freezing instead. Ice crawling up his arms, his neck, his face, a message telling him he's absorbing the frost queen's core, and he'll stay in hibernation until it's fully absorbed. That's the last thing he sees for 25 years. Now, 76 hours before this fight, five heroes are standing in front of that dungeon, and there's a problem.

**candidate** `p0005_01, p0005_02, p0005_04, p0005_06, p0005_08, p0005_10`

As she dissolves into light, the Frost Queen smiles and admits that their duel was fun. Jun-Ho stares back coldly, replying that he cannot say the same. He delivers one final strike, but his eyes widen when a thick frost crawls up his skin. He cries out as the relentless ice consumes his face.

### Beat 5

**reference** 

Only one of them can go up those stairs. The big tattooed guy is punching the ice wall, furious that picking one person is the same as telling the rest to die. The cowboy tips his hat and admits they're at a disadvantage, but everyone already knows who has to go. Even the big guy concedes.

**candidate** `p0005_11, p0005_12, p0005_14, p0006_02, p0006_03, p0006_04, p0006_05, p0006_06, p0006_07, p0006_08, p0006_09`

A system prompt alerts Jun-Ho that his body must hibernate to absorb her nucleus, flashing back to when Khali, a heavily tattooed member of the original five heroes, punched an ice wall in frustration. Skaya nominated him to climb the final stairs alone, which was supported by The Marksman due to elemental disadvantages.

### Beat 6

**reference** 

There's really no one quite like Spectre. The girl agrees, and just like that, four people hand their lives to one man. The whole squad stands facing him, telling him they know their deaths won't be meaningless. He mumbles that not a lot of people would call him their friend.

**candidate** `p0007_02, p0007_03, p0007_04, p0007_05, p0007_06, p0007_07`

Khali clicks his tongue and admits his frustration about staying behind. He eventually concedes because no one else compares to Specter. The Swordswoman observes that his fast agreement confirms their unanimous vote. Khali barks a retort at her jab, yet she remains serious about sending Jun-Ho alone.

### Beat 7

**reference** 

The cowboy just smiles and says they'd follow him even to death. The healer beams at him saying none of it will be in vain and all he can get out is a quiet you guys before apologizing and walking up those stairs alone. 25 years later, the year is 2024 and we're at a museum exhibit about the monsters humanity still can't defeat. A presenter explains how one man froze the Pacific with a snap of the frost queen's fingers and how five legends walked into Antarctica to stop her.

**candidate** `p0007_08, p0007_09, p0007_10, p0007_11, p0008_02, p0008_03`

He asks if they will regret this, but The Marksman replies they trust him.

### Beat 8

**reference** 

Those five are displayed right there, frozen in ice. the five heroes. Then a nerdy kid starts screaming, pointing at the exhibit. The ice statue just moved.

**candidate** `p0008_04, p0008_05, p0008_06, p0008_07, p0008_08, p0008_09`

Skaya, Khali and The Swordswoman tell Jun-Ho that only he can succeed.

### Beat 9

**reference** 

The presenter laughs it off, explaining the chamber's temperature is controlled 24/7. There's no way anything happens to those statues. Then she hears the cracking behind her. The ice explodes and a figure burst out of the shards.

**candidate** `p0008_10, p0008_11, p0008_12, p0008_13, p0009_01, p0009_02, p0009_03, p0009_04, p0009_05, p0009_06`

Twenty-five years later, a presenter in a black suit with black hair explains the legacy of the final dungeon team to an audience, unveiling the ice statues of the five legendary heroes, including the frozen body of Jun-Ho.

### Beat 10

**reference** 

He drops to his knees, shaking as a message tells him the absorption finally hit 100%. The only thing Bro can say after 25 years, co and a new notification, X-rank skill acquired. Frost, the news detonates worldwide within hours. The legend has awakened.

**candidate** `p0009_07, p0009_08, p0009_09, p0009_10, p0010_03, p0010_04`

Deep within the frozen monument, the hand of Seo Jun-Ho suddenly twitches beneath the surface. A schoolboy points excitedly and says that the ice statue just moved. The presenter, a museum historian, tells him he is wrong while the ice cracks. The casing shatters with a violent boom, forcing him to admit it is impossible.

### Beat 11

**reference** 

The spectre is back after 25 years of cryogenic sleep. Meanwhile, the legend himself is sitting in a hospital bed, scrolling headlines like a grandpa who just discovered the internet. It's been 25 years. He tries to make a fist and can barely close his fingers.

**candidate** `p0010_05, p0010_06, p0010_08, p0011_01, p0011_02, p0011_03`

The monument erupts as he bursts through his frozen shell, sending the presenter stumbling back. He collapses and shivers in the open air, thinking that it is incredibly cold. System prompts announce that he has absorbed the queen’s nucleus and gained Frost (EX), a rank representing extraordinary power levels.

### Beat 12

**reference** 

The doctors walk in with news. The president of the player association is coming to see him personally. Joan Hull already hates this if it's not someone he knows he's sending them away. But the doctor says the man used to talk with the spectre all the time, a close friend.

**candidate** `p0011_04, p0011_05, p0011_06, p0012_01, p0012_02, p0012_03, p0012_04`

Jun-Ho collapses on the shattered floor while the panicked presenter asks what is happening. Holographic news feeds immediately report that the legendary Specter has finally returned after his long slumber. Resting in a quiet hospital bed, he marvels that twenty-five years have actually passed. His fingers tremble as he admits he can barely clench his hands.

### Beat 13

**reference** 

And when the guy shows up, bro instantly recognizes him. It's Shimuk. And just like he predicted 25 years ago, dude went completely bald. That's the first thing he says after a 25-year reunion.

**candidate** `p0012_07, p0012_09, p0012_10, p0012_12, p0012_14, p0013_01, p0013_02, p0013_03, p0013_04, p0013_05, p0013_07`

When a doctor announces the arrival of the association president, he looks out at the sprawling modern skyscrapers, realizing his friends achieved their dream of a peaceful world.

### Beat 14

**reference** 

Shim is furious, saying he was dumb for expecting an emotional moment. Once they're alone, Jono asks the real question. Why is everyone acting weird when the war should be over? So Shim explains, "The day they killed the Frost Queen, the whole world celebrated for about a minute.

**candidate** `p0013_08, p0013_12, p0013_15, p0013_16, p0013_17, p0013_18`

As he holds his mask, the chief doctor gasps, calls him Specter, and asks why he is taking it off.

### Beat 15

**reference** 

Then a new message dropped. A dimensional elevator appeared in the Pacific, and the second floor was now open. 10 floors total. His team took 5 years to clear the first one.

**candidate** `p0014_01, p0014_03, p0014_04, p0014_05, p0014_07, p0014_08`

Jun-Ho stares in disbelief as Deok-gu, his old friend and the current President enters and dismisses the bowing doctors.

### Beat 16

**reference** 

So after 25 years, humanity should be around floor 7, right? Shim can barely say it. In 25 years, humanity cleared one floor. Bro almost falls over.

**candidate** `p0014_09, p0014_10, p0014_11, p0015_01, p0015_02, p0015_03`

Deok-gu tells his friend that Jun-Ho looks exactly the same as he always did. Recognizing that distinct voice, he laughs and asks how his old companion developed such severe M-pattern baldness. He calls it a touching reunion while Deok-gu rubs his head and mutters that he hasn't changed one bit.

### Beat 17

**reference** 

25 years, one floor. But there's a reason. The third floor is a sea of lava. And the only way to cool it down is an altar that needs the frost queen's core.

**candidate** `p0015_04, p0015_06, p0015_07, p0015_08, p0016_05, p0016_06`

Jun-Ho shifts the topic, and Deok-gu recalls when the system announced their final dungeon victory.

### Beat 18

**reference** 

They search the nest for decades and never found it. And Jono just goes quiet because he knows exactly where that core is. He at it. It's inside him right now.

**candidate** `p0016_07, p0016_08, p0016_09, p0016_10, p0016_11, p0016_13, p0016_16`

Humanity rejoices, but a sudden system message shatters the peace, declaring a dimensional elevator is installed in the Pacific Ocean.

### Beat 19

**reference** 

So he forgives them with the straightest face possible for a mistake they never made. Later, he sneaks out to the history museum, and there they are, his four friends, still frozen, on display like trophies. He sits down, apologizes for being late, and asks them to have a drink with him. But the moment he touches the ice, a message appears.

**candidate** `p0016_18, p0016_19, p0016_20, p0017_02, p0017_03, p0017_04`

As the system opens the Frontier, world leaders meet. He says their expedition to the second floor brings back vast knowledge.

### Beat 20

**reference** 

The skill frost axe can free them from the frozen prison, but his magic stat is too low. Seal removal failed. His stats went back to level one after the hibernation, but every floor of the elevator cleared gives a permanent boost. So, the plan writes itself.

**candidate** `p0017_05, p0017_06, p0017_07, p0017_10, p0018_01, p0018_02`

Jun-Ho asks what came next while Deok-gu describes the Dimensional Elevator, a spire rising from the Pacific. His old friend reveals that the structure contains ten floors in total. He calculates that humanity should have reached the seventh floor by now. He stares past Deok-gu at the ghosts of his team and weighs their accomplishments.

### Beat 21

**reference** 

Climb the tower, get the magic, melt the ice, bring them home. He tells Shim he's becoming a player again.

**candidate** `p0018_03, p0018_04, p0018_06, p0018_09, p0018_12, p0018_13, p0018_14, p0018_16`

Deok-gu, Jun-Ho's old friend and the current President, says they are only on the second floor, leaving Jun-Ho utterly speechless.

### Beat 22

**reference** 

(no reference beat)

**candidate** `p0019_01, p0019_02, p0019_03, p0019_04, p0019_05, p0019_09, p0019_10, p0019_11, p0019_12, p0019_13`

He sits up in fury, demanding an explanation, and Deok-gu explains that the third floor is a volcanic wasteland requiring the Frost Queen's nucleus to cool.

### Beat 23

**reference** 

(no reference beat)

**candidate** `p0020_01, p0020_02, p0020_03, p0020_04, p0020_05, p0020_06`

Deok-gu says they searched the nest in vain. Still, Jun-Ho knows that he already absorbed it.

### Beat 24

**reference** 

(no reference beat)

**candidate** `p0020_07, p0020_08, p0020_10, p0020_11, p0020_12, p0020_14`

Jun-Ho rests a hand on his friend’s shoulder and tells Deok-gu they were just unlucky. He says they should be understanding because anyone can make a mistake. Deok-gu cries and gazes up before shouting with a sudden, radiant burst of relief. He smiles serenely while his companion finally lets a heavy burden fall.

### Beat 25

**reference** 

(no reference beat)

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
