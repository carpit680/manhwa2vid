# Script comparison — reference vs generated

Reference: `reference/frozen_player/mamoru_ch1-2.txt` · Candidate: `projects/return-of-the-frozen-player-ch1-2/script.json`

## Content (does it tell the same story?)

- fact_coverage: **0.49** of 303 salient reference terms
- order_tau: **0.27** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): answer, 25 years, precise, humanity's, she's, feels, make, whole, understands, bro, cuts, fool, forms, pure, answers, simple, i'll, nightmare, midair, trading, goku, goku's, speed, fires, blank

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 21 | 28 |
| words | 979 | 1436 |
| avg_sentence_words | 11.9 | 13.7 |
| caption_markers_per_100w | 0.0 | 0.0 |
| speech_verbs_per_100w | 1.43 | 2.79 |
| connectives_per_100w | 4.19 | 2.99 |
| max_consecutive_pronoun_starts | 3 | 3 |
| pronoun_start_fraction | 0.2 | 0.31 |

## Side by side

### Beat 1

**reference** 

To answer that, we have to go back 25 years to be precise. Humanity's final dungeon, and standing at the end of it is the Frost Queen, the monster that froze the Pacific Ocean with a snap. She's laughing in his face, asking how it feels to make it this far. After leaving his whole team behind to die, she tells him he understands nothing about this world.

**candidate** `p0001_02, p0001_03, p0001_04, p0001_05, p0001_06, p0001_07, p0002_01, p0002_02, p0002_03, p0002_04, p0002_05, p0002_06`

Seo Jun-Ho, legendary hero, enters the throne room as his blade glows with power. A system alert confirms his arrival at the Antarctic gate, a supernatural dungeon portal, where the Frost Queen mocks him. He warns his comrades will not die easily and tells her to shut it.

### Beat 2

**reference** 

But Bro cuts her off, saying he's got no time to fool around. She forms a giant blade of pure ice, and he answers with a simple, "I'll kill you and end this nightmare." The two collide midair, trading blows at Goku's speed. She gathers ice magic in her hand and fires it point blank. He dodges by a hair.

**candidate** `p0002_09, p0002_10, p0002_11, p0003_01, p0003_02, p0003_03`

A boot shatters the frozen floor as Jun-Ho and the Frost Queen collide. These warriors trade rapid blows in the throne room, showering the chamber in brilliant sparks of energy. He braces himself as a massive burst of ice magic suddenly pushes him backward.

### Beat 3

**reference** 

Then in one final exchange, a black flash cuts through the blue silence. The frost queen is on her knees and the guy is standing behind her. She says it was fun. He says he can't say the same.

**candidate** `p0003_04, p0003_05, p0003_06, p0004_01, p0004_02, p0004_03, p0004_04, p0004_05`

The Frost Queen smiles while gathering a lethal surge of freezing magic in her palm. Jun-Ho thinks this is impossible just before a blinding explosion tears through the room. He drops into a low crouch while jagged ice shards and dark energy swirl around him. A faint blue light flickers as he stands over his defeated opponent.

### Beat 4

**reference** 

He moves in to finish it, but the moment she starts to glow, his body starts freezing instead. Ice crawling up his arms, his neck, his face, a message telling him he's absorbing the frost queen's core, and he'll stay in hibernation until it's fully absorbed. That's the last thing he sees for 25 years. Now, 76 hours before this fight, five heroes are standing in front of that dungeon, and there's a problem.

**candidate** `p0005_01, p0005_02, p0005_04, p0005_06, p0005_08, p0005_10, p0005_11`

The Frost Queen begins to dissolve into light and admits the battle was fun. Jun-Ho stares her down and replies that he cannot say the same. He delivers a final strike but gasps as creeping frost suddenly climbs his skin. A system alert declares his hibernation is mandatory to absorb her nucleus, a monster's core.

### Beat 5

**reference** 

Only one of them can go up those stairs. The big tattooed guy is punching the ice wall, furious that picking one person is the same as telling the rest to die. The cowboy tips his hat and admits they're at a disadvantage, but everyone already knows who has to go. Even the big guy concedes.

**candidate** `p0005_12, p0005_14, p0006_02, p0006_03, p0006_04, p0006_05, p0006_06, p0006_07, p0006_08, p0006_09`

Twenty-five years ago in Antarctica, the five-member hero party reached the final dungeon doorway only for a system message to declare that only one person could proceed. Khali, the tattooed giant of the original five-member hero party, punches the ice wall in immense frustration.

### Beat 6

**reference** 

There's really no one quite like Spectre. The girl agrees, and just like that, four people hand their lives to one man. The whole squad stands facing him, telling him they know their deaths won't be meaningless. He mumbles that not a lot of people would call him their friend.

**candidate** `p0007_02, p0007_03, p0007_04, p0007_05, p0007_06, p0007_07`

A frustrated click of the tongue rings out as Khali clenches his jaw. He admits his resentment but yields because no hunter matches the strength of Jun-Ho. The swordswoman, the party's front-line fighter, teases him for yielding so fast. She remains serious while agreeing their legendary ally must be the one to go.

### Beat 7

**reference** 

The cowboy just smiles and says they'd follow him even to death. The healer beams at him saying none of it will be in vain and all he can get out is a quiet you guys before apologizing and walking up those stairs alone. 25 years later, the year is 2024 and we're at a museum exhibit about the monsters humanity still can't defeat. A presenter explains how one man froze the Pacific with a snap of the frost queen's fingers and how five legends walked into Antarctica to stop her.

**candidate** `p0007_08, p0007_09, p0007_10, p0007_11, p0008_02, p0008_03`

Jun-Ho stands a short distance away from his four trusted companions. He looks at Khali and Skaya. Beside them stand the marksman and the swordswoman. He asks the group if they are sure they will not regret their decision. A voice questions if regret is even possible.

### Beat 8

**reference** 

Those five are displayed right there, frozen in ice. the five heroes. Then a nerdy kid starts screaming, pointing at the exhibit. The ice statue just moved.

**candidate** `p0008_04, p0008_05, p0008_06, p0008_07, p0008_08, p0008_09`

Skaya smiles while clutching her staff and tells Jun-Ho that their deaths will not be in vain. He thinks of his comrades as they apologize for the heavy burden they are leaving him. They stand together one last time and insist that only he can finish this fight.

### Beat 9

**reference** 

The presenter laughs it off, explaining the chamber's temperature is controlled 24/7. There's no way anything happens to those statues. Then she hears the cracking behind her. The ice explodes and a figure burst out of the shards.

**candidate** `p0008_10, p0008_11, p0008_12, p0008_13, p0009_01, p0009_02, p0009_03, p0009_04, p0009_05, p0009_06`

Twenty-five years pass, and the narrative shifts to a modern exhibition hall where a presenter in a black suit details the historical terror of the Frost Queen. When a schoolboy asks about the legendary expedition team, the presenter snaps his fingers to unveil the five frozen heroes, including Jun-Ho, preserved in solid ice.

### Beat 10

**reference** 

He drops to his knees, shaking as a message tells him the absorption finally hit 100%. The only thing Bro can say after 25 years, co and a new notification, X-rank skill acquired. Frost, the news detonates worldwide within hours. The legend has awakened.

**candidate** `p0009_07, p0009_08, p0009_09, p0009_10, p0010_03, p0010_04`

A frozen hand twitches as the schoolboy shouts that the statue is moving. Dismissing his claim as a mistake, the presenter turns away. The monument of him shatters into jagged pieces while his teammates remain frozen. She gasps that such an event is impossible.

### Beat 11

**reference** 

The spectre is back after 25 years of cryogenic sleep. Meanwhile, the legend himself is sitting in a hospital bed, scrolling headlines like a grandpa who just discovered the internet. It's been 25 years. He tries to make a fist and can barely close his fingers.

**candidate** `p0010_05, p0010_06, p0010_08, p0011_01, p0011_02`

He bursts violently from his frozen prison as the central ice monument explodes. He tumbles through a shower of flying shards and falls toward the museum floor. Collapsing onto the hard ground, he shivers intensely among the scattered remnants of ice. Shuddering from the sudden warmth, he finally breathes the outside air and mutters that it is cold.

### Beat 12

**reference** 

The doctors walk in with news. The president of the player association is coming to see him personally. Joan Hull already hates this if it's not someone he knows he's sending them away. But the doctor says the man used to talk with the spectre all the time, a close friend.

**candidate** `p0011_03, p0011_04, p0011_05, p0011_06, p0012_01, p0012_02, p0012_03`

The presenter asks what is happening as a notification confirms Jun-Ho received the EX-rank Frost skill. While news screens announce the Specter has returned, he sits in a hospital bed. He asks Shim Deok-gu, the Player Association president, if twenty-five years have really passed. Studying his trembling fingers, he admits he can barely clench his hands.

### Beat 13

**reference** 

And when the guy shows up, bro instantly recognizes him. It's Shimuk. And just like he predicted 25 years ago, dude went completely bald. That's the first thing he says after a 25-year reunion.

**candidate** `p0012_04, p0012_07, p0012_09, p0012_10, p0012_12, p0012_14`

He clenches his trembling hands, testing the limits of his weakened body. The chief doctor, the hospital’s lead physician, enters to announce that the Association president is arriving. He chuckles and thanks the man while admitting that very few people would still call him a friend.

### Beat 14

**reference** 

Shim is furious, saying he was dumb for expecting an emotional moment. Once they're alone, Jono asks the real question. Why is everyone acting weird when the war should be over? So Shim explains, "The day they killed the Frost Queen, the whole world celebrated for about a minute.

**candidate** `p0013_01, p0013_02, p0013_03, p0013_04, p0013_05, p0013_07`

He gazes through the glass at the towering skyscrapers of a world he barely recognizes. Even as the city thrives, he cannot ignore the heavy silence of the friends he left behind.

### Beat 15

**reference** 

Then a new message dropped. A dimensional elevator appeared in the Pacific, and the second floor was now open. 10 floors total. His team took 5 years to clear the first one.

**candidate** `p0013_08, p0013_12, p0013_15, p0013_16, p0013_17, p0013_18`

Jun-Ho holds his signature mask, weighing the cost of hiding his face again. He leaves it lowered as the chief doctor enters and stammers the name Specter. Awed by the sight, the physician asks why the legend would finally reveal his appearance. The young doctor, a junior resident, and the nurse, a clinic assistant, freeze in shock.

### Beat 16

**reference** 

So after 25 years, humanity should be around floor 7, right? Shim can barely say it. In 25 years, humanity cleared one floor. Bro almost falls over.

**candidate** `p0014_01, p0014_03, p0014_04, p0014_05, p0014_07, p0014_08`

Before the doctors can recover, Shim Deok-gu enters the room accompanied by his bodyguards. He requests a private conversation with Jun-Ho, prompting the awestruck hospital staff to bow and leave the room immediately.

### Beat 17

**reference** 

25 years, one floor. But there's a reason. The third floor is a sea of lava. And the only way to cool it down is an altar that needs the frost queen's core.

**candidate** `p0014_09, p0014_10, p0014_11, p0015_01, p0015_02, p0015_03`

Shim Deok-gu marvels that Jun-Ho looks exactly as he did decades ago. Recognizing the familiar voice, he laughs and points out his friend's severe M-pattern baldness. The president snaps at the lack of respect while he calls it a touching reunion. Sighing, Deok-gu pulls up a chair and admits that he hasn't changed at all.

### Beat 18

**reference** 

They search the nest for decades and never found it. And Jono just goes quiet because he knows exactly where that core is. He at it. It's inside him right now.

**candidate** `p0015_04, p0015_06, p0015_07, p0015_08, p0016_05, p0016_06`

He shifts the conversation to a more serious topic. He prepares to share the difficult news of how the world changed. But his friend recalls that every player heard the exact same message. Twenty-five years ago, a system announcement declares the final boss defeated. Deok-gu shouts in joy that his companion finally won. Then, the system proclaims that safe zones will now appear across Earth.

### Beat 19

**reference** 

So he forgives them with the straightest face possible for a mistake they never made. Later, he sneaks out to the history museum, and there they are, his four friends, still frozen, on display like trophies. He sits down, apologizes for being late, and asks them to have a drink with him. But the moment he touches the ice, a message appears.

**candidate** `p0016_07, p0016_08, p0016_09, p0016_10, p0016_11, p0016_13`

The jubilant citizens rejoice in the streets, crying tears of joy over the hard-won victory. Yet he warns that the world does not let their relief last even for a single minute. A sudden chime rings as the system announces that a dimensional elevator is now installed in the Pacific Ocean. The startled audience members gasp in utter disbelief at the sudden notification.

### Beat 20

**reference** 

The skill frost axe can free them from the frozen prison, but his magic stat is too low. Seal removal failed. His stats went back to level one after the hibernation, but every floor of the elevator cleared gives a permanent boost. So, the plan writes itself.

**candidate** `p0016_16, p0016_18, p0016_19, p0016_20, p0017_02, p0017_03, p0017_04, p0017_05, p0017_06, p0017_07, p0017_10`

The system announced access to the Frontier Area, prompting global leaders and politicians to hold emergency meetings. Deok-gu explains that humanity conquered the second floor, gaining immense magic and resources, but Jun-Ho is shocked to learn that the Dimensional Elevator consists of ten floors. Based on the timeline, he calculates that they should have reached the seventh floor by now.

### Beat 21

**reference** 

Climb the tower, get the magic, melt the ice, bring them home. He tells Shim he's becoming a player again.

**candidate** `p0018_01, p0018_02, p0018_03, p0018_04, p0018_06, p0018_09`

Jun-Ho looks down solemnly while comparing the current era to his own past. Behind him stand the ghostly figures of his former comrades. He stands before the spirit of Khali. Beside him is Skaya. The marksman also stands there. Finally, the swordswoman joins them. He asks Shim Deok-gu their current floor. His old friend remains completely silent and looks down.

### Beat 22

**reference** 

(no reference beat)

**candidate** `p0018_12, p0018_13, p0018_14, p0018_16, p0019_01, p0019_02`

Shim Deok-gu reveals their pathetic progress, and Jun-Ho collapses onto the mattress in total disbelief. Covering his face, he mutters that he has nothing to say after twenty-five wasted years. He bolts upright as a green aura flares, demanding how they only cleared the second floor.

### Beat 23

**reference** 

(no reference beat)

**candidate** `p0019_03, p0019_04, p0019_05, p0019_09, p0019_10, p0019_11, p0019_12`

Jun-Ho glares at a sweating Shim Deok-gu. He tells his old friend that he is listening only because he is curious. The two men face each other as the tension in the room grows heavy. But his fury only mounts, while the older man remains solemnly silent in the face of his anger.

### Beat 24

**reference** 

(no reference beat)

**candidate** `p0019_13, p0020_01, p0020_02, p0020_03, p0020_04, p0020_05`

Shim Deok-gu says only certain players can withstand the magma. He tells Jun-Ho that they discovered an ancient altar floating in the lava. This altar requires the Frost Queen's Nucleus to cool the surrounding heat. Clutching his forehead, Deok-gu says they searched the Nest countless times without success.

### Beat 25

**reference** 

(no reference beat)

**candidate** `p0020_06, p0020_07, p0020_08, p0020_10, p0020_11, p0020_12, p0020_14, p0020_15`

Jun-Ho rests a hand on his friend's shoulder to ease the heavy guilt. He tells Shim Deok-gu that the players were simply unlucky and their failure was an understandable mistake. Deok-gu shouts in joyful disbelief at the kindness. Watching the outburst, he mutters a curse and offers an awkward, sweating smile.

### Beat 26

**reference** 

(no reference beat)

**candidate** `p0021_01, p0021_12, p0021_13, p0022_01, p0022_02, p0022_03, p0022_04, p0022_05, p0022_06, p0022_07`

Jun-Ho wonders how to break the news to his friend without triggering a massive lecture. Since Shim Deok-gu warns him about reporters waiting downstairs, he agrees to stay hidden. He enters the museum vault via biometric security and passes a displayed dragon skeleton. Reaching his frozen comrades, he sits and whispers an apology for being so late.

### Beat 27

**reference** 

(no reference beat)

**candidate** `p0023_01, p0023_02, p0023_04, p0023_05, p0023_06, p0023_07`

The museum vault is silent as he recalls their shared laughter. He tells his sleeping comrades the peace they dreamed of is finally safe. Liquid splashes into paper cups as he invites his friends to have a drink. Sitting on the floor, he tells the team they can finally rest.

### Beat 28

**reference** 

(no reference beat)

**candidate** `p0023_08, p0023_09, p0023_10, p0023_12, p0023_13, p0024_01, p0024_03`

Jun-Ho takes a slow drink of his alcohol and looks up at his frozen teammates. They stand bathed in a bright beam of light inside the quiet room. He gazes at the icy face of Skaya. He asks his silent friends if the sweet drink tastes good to them, then mutters a curse.
