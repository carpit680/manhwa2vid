# Script comparison — reference vs generated

Reference: `reference/frozen_player/mamoru_ch1-2.txt` · Candidate: `projects/return-of-the-frozen-player-ch1-2/script.json`

## Content (does it tell the same story?)

- fact_coverage: **0.47** of 303 salient reference terms
- order_tau: **0.24** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): answer, 25 years, precise, she's, feels, leaving, bro, cuts, fool, around, forms, giant, pure, answers, simple, i'll, nightmare, midair, trading, goku, goku's, speed, fires, point, blank

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 21 | 28 |
| words | 979 | 1337 |
| avg_sentence_words | 11.9 | 15.5 |
| caption_markers_per_100w | 0.0 | 0.07 |
| speech_verbs_per_100w | 1.43 | 2.32 |
| connectives_per_100w | 4.19 | 2.69 |
| max_consecutive_pronoun_starts | 3 | 2 |
| pronoun_start_fraction | 0.2 | 0.26 |

## Side by side

### Beat 1

**reference** 

To answer that, we have to go back 25 years to be precise. Humanity's final dungeon, and standing at the end of it is the Frost Queen, the monster that froze the Pacific Ocean with a snap. She's laughing in his face, asking how it feels to make it this far. After leaving his whole team behind to die, she tells him he understands nothing about this world.

**candidate** `p0001_02, p0001_03, p0001_04, p0001_05, p0001_06, p0001_07`

Seo Jun-Ho, a legendary hero also known as Specter stands in the Frost Queen’s Nest. The Frost Queen, the boss of the final Antarctic dungeon, mocks him for abandoning his comrades. He refuses to believe they would perish easily and grips his blade.

### Beat 2

**reference** 

But Bro cuts her off, saying he's got no time to fool around. She forms a giant blade of pure ice, and he answers with a simple, "I'll kill you and end this nightmare." The two collide midair, trading blows at Goku's speed. She gathers ice magic in her hand and fires it point blank. He dodges by a hair.

**candidate** `p0002_01, p0002_02, p0002_03, p0002_04, p0002_05, p0002_06`

The Frost Queen laughs at his confidence and asks if he truly thinks the fight is over. She sneers that he is ignorant about the world, but Jun-Ho tells her to shut it. Dark energy swirls as he admits he has no time for games and finally vows to kill her where she stands.

### Beat 3

**reference** 

Then in one final exchange, a black flash cuts through the blue silence. The frost queen is on her knees and the guy is standing behind her. She says it was fun. He says he can't say the same.

**candidate** `p0002_09, p0002_10, p0002_11, p0003_01, p0003_02, p0003_03`

A heavy boot shatters the icy ground as Jun-Ho launches himself upward. Mid-air, he collides violently with the Frost Queen. Furious blows trade back and forth in the center of the throne room, scattering bright sparks. But a sudden, massive burst of ice energy forces him back as he struggles to brace himself.

### Beat 4

**reference** 

He moves in to finish it, but the moment she starts to glow, his body starts freezing instead. Ice crawling up his arms, his neck, his face, a message telling him he's absorbing the frost queen's core, and he'll stay in hibernation until it's fully absorbed. That's the last thing he sees for 25 years. Now, 76 hours before this fight, five heroes are standing in front of that dungeon, and there's a problem.

**candidate** `p0003_04, p0003_05, p0003_06, p0004_01, p0004_02, p0004_03, p0004_04, p0004_05`

The Frost Queen smiles with lethal confidence as her hands ignite with raw magical energy. Jun-Ho gasps in shock at the sudden surge, bracing for a strike that levels the throne room. A blinding explosion throws them apart while the frozen floor shatters into jagged shards. He lands in a low crouch, watching the queen finally fall before him.

### Beat 5

**reference** 

Only one of them can go up those stairs. The big tattooed guy is punching the ice wall, furious that picking one person is the same as telling the rest to die. The cowboy tips his hat and admits they're at a disadvantage, but everyone already knows who has to go. Even the big guy concedes.

**candidate** `p0005_01, p0005_02, p0005_04, p0005_06, p0005_08, p0005_10`

The Frost Queen begins to vanish into light, admitting that their battle was fun. Jun-Ho looks down coldly and tells her he cannot say the same. He lands one final, explosive strike that triggers a massive burst of energy. Suddenly, jagged ice creeps across his skin, and he gasps in shock as the frost seals his face.

### Beat 6

**reference** 

There's really no one quite like Spectre. The girl agrees, and just like that, four people hand their lives to one man. The whole squad stands facing him, telling him they know their deaths won't be meaningless. He mumbles that not a lot of people would call him their friend.

**candidate** `p0005_11, p0005_12, p0005_14, p0006_02, p0006_03, p0006_04, p0006_05, p0006_06, p0006_07, p0006_08, p0006_09`

A system message explains that his body must go into hibernation to absorb the nucleus, flashing back to Antarctica twenty-five years ago when Skaya, a member of the original five heroes, currently frozen in ice, Khali, a member of the original five heroes, currently frozen in ice, and The Marksman, a member of the original five heroes, currently frozen in ice, chose Jun-Ho to go alone due to their elemental ice disadvantage.

### Beat 7

**reference** 

The cowboy just smiles and says they'd follow him even to death. The healer beams at him saying none of it will be in vain and all he can get out is a quiet you guys before apologizing and walking up those stairs alone. 25 years later, the year is 2024 and we're at a museum exhibit about the monsters humanity still can't defeat. A presenter explains how one man froze the Pacific with a snap of the frost queen's fingers and how five legends walked into Antarctica to stop her.

**candidate** `p0007_02, p0007_03, p0007_04, p0007_05, p0007_06, p0007_07`

Although Khali is frustrated, he concedes to his teammate's superior skills while The Swordswoman, a member of the original five heroes, currently frozen in ice, agrees that he is the best choice to succeed.

### Beat 8

**reference** 

Those five are displayed right there, frozen in ice. the five heroes. Then a nerdy kid starts screaming, pointing at the exhibit. The ice statue just moved.

**candidate** `p0007_08, p0007_09, p0007_10, p0007_11, p0008_02, p0008_03`

Facing his friends, he asks if they are certain they won't regret this choice. The Marksman currently frozen in ice, admits they might if he loses. He tells him that they have total faith, and the hero stares ahead in silence.

### Beat 9

**reference** 

The presenter laughs it off, explaining the chamber's temperature is controlled 24/7. There's no way anything happens to those statues. Then she hears the cracking behind her. The ice explodes and a figure burst out of the shards.

**candidate** `p0008_04, p0008_05, p0008_06, p0008_07, p0008_08, p0008_09`

Skaya smiles warmly and tells Jun-Ho that she knows he will not let their deaths be in vain. A final apology follows as he whispers to his friends and the somber memory finally starts to dissolve.

### Beat 10

**reference** 

He drops to his knees, shaking as a message tells him the absorption finally hit 100%. The only thing Bro can say after 25 years, co and a new notification, X-rank skill acquired. Frost, the news detonates worldwide within hours. The legend has awakened.

**candidate** `p0008_10, p0008_11, p0008_12, p0008_13, p0009_01, p0009_02`

Twenty-five years fly by, bringing the story to a modern era beneath a clear blue sky. A large white building stands on a grassy hill, hosting a historical lecture. The presenter tells a gathered audience about the logic-defying monsters humanity once faced. He says the Frost Queen froze the entire Pacific Ocean with a single wave of her hand. The presenter replies that they did.

### Beat 11

**reference** 

The spectre is back after 25 years of cryogenic sleep. Meanwhile, the legend himself is sitting in a hospital bed, scrolling headlines like a grandpa who just discovered the internet. It's been 25 years. He tries to make a fist and can barely close his fingers.

**candidate** `p0009_03, p0009_04, p0009_05, p0009_06, p0009_07, p0009_08, p0009_09, p0009_10`

The presenter snaps his fingers to display the ice statues of the legendary squad, unaware that the monument containing he is beginning to crack.

### Beat 12

**reference** 

The doctors walk in with news. The president of the player association is coming to see him personally. Joan Hull already hates this if it's not someone he knows he's sending them away. But the doctor says the man used to talk with the spectre all the time, a close friend.

**candidate** `p0010_03, p0010_04, p0010_05, p0010_06, p0010_08, p0011_01, p0011_02, p0011_03, p0011_04, p0011_05, p0011_06`

The presenter looks back in confusion just before the ice encasing Jun-Ho shatters with a violent boom. After absorbing the queen's nucleus, he bursts out and collapses while the system grants him Frost (EX), an extraordinary tier of power. Shivering, he gasps that it is freezing as the presenter asks what is happening.

### Beat 13

**reference** 

And when the guy shows up, bro instantly recognizes him. It's Shimuk. And just like he predicted 25 years ago, dude went completely bald. That's the first thing he says after a 25-year reunion.

**candidate** `p0012_01, p0012_02, p0012_03, p0012_04, p0012_07, p0012_09`

A holographic news window announces the awakening of the legendary Specter after twenty-five years of cryogenic sleep. Staring at the floating screens, he realizes in disbelief how much time has passed. Strength has completely left his body, making it difficult to even clench his trembling hands. He stares down at his fingers shaking with strain on the table.

### Beat 14

**reference** 

Shim is furious, saying he was dumb for expecting an emotional moment. Once they're alone, Jono asks the real question. Why is everyone acting weird when the war should be over? So Shim explains, "The day they killed the Frost Queen, the whole world celebrated for about a minute.

**candidate** `p0012_10, p0012_12, p0012_14, p0013_01, p0013_02, p0013_03`

As the chief doctor, the facility's lead physician, observes him, Jun-Ho sits on his bed. He looks down at his open palm and thanks the man for the heads-up. Visions of frozen comrades drift through his mind, featuring Skaya and Khali. He also recalls his frozen allies, The Marksman, and The Swordswoman, who both remain trapped in ice.

### Beat 15

**reference** 

Then a new message dropped. A dimensional elevator appeared in the Pacific, and the second floor was now open. 10 floors total. His team took 5 years to clear the first one.

**candidate** `p0013_04, p0013_05, p0013_07, p0013_08, p0013_12, p0013_15`

He looks out at the high-tech skyline his friends sacrificed everything to build. He reflects that they finally achieved the peace they wanted while he slept. Rest ends today as he prepares to don his black mask once more. The legendary Specter returns to the shadows to finish their work.

### Beat 16

**reference** 

So after 25 years, humanity should be around floor 7, right? Shim can barely say it. In 25 years, humanity cleared one floor. Bro almost falls over.

**candidate** `p0013_16, p0013_17, p0013_18, p0014_01, p0014_03, p0014_04`

Jun-Ho takes off his mask to the shock of the medical staff just as Deok-gu, his old friend and the current President of the Player Association enters with his bodyguards.

### Beat 17

**reference** 

25 years, one floor. But there's a reason. The third floor is a sea of lava. And the only way to cool it down is an altar that needs the frost queen's core.

**candidate** `p0014_05, p0014_07, p0014_08, p0014_09, p0014_10, p0014_11`

Jun-Ho stares in utter shock at the balding stranger standing before his bed. Deok-gu clears his throat to ask the medical staff for a private moment alone. He remarks that his old friend looks exactly the same. Recognizing that voice, he smiles and admits he finally knows it is truly him.

### Beat 18

**reference** 

They search the nest for decades and never found it. And Jono just goes quiet because he knows exactly where that core is. He at it. It's inside him right now.

**candidate** `p0015_01, p0015_02, p0015_03, p0015_04, p0015_06, p0015_07`

Jun-Ho howls with laughter while mocking the M-pattern baldness claiming his old friend’s scalp. Deok-gu bristles but admits that his comrade has not changed one bit. The levity vanishes once his expression turns sharp to ask about the world’s current status. Deok-gu looks away to share the grim news of humanity's stalled progress.

### Beat 19

**reference** 

So he forgives them with the straightest face possible for a mistake they never made. Later, he sneaks out to the history museum, and there they are, his four friends, still frozen, on display like trophies. He sits down, apologizes for being late, and asks them to have a drink with him. But the moment he touches the ice, a message appears.

**candidate** `p0015_08, p0016_05, p0016_06, p0016_07, p0016_08, p0016_09, p0016_10, p0016_11, p0016_13, p0016_16`

In a flashback, the world celebrated his historic victory until the system suddenly announced that a Dimensional Elevator had been installed in the Pacific Ocean.

### Beat 20

**reference** 

The skill frost axe can free them from the frozen prison, but his magic stat is too low. Seal removal failed. His stats went back to level one after the hibernation, but every floor of the elevator cleared gives a permanent boost. So, the plan writes itself.

**candidate** `p0016_18, p0016_19, p0016_20, p0017_02, p0017_03, p0017_04`

Global leaders met to address the second floor, sending an expedition squad to the frontier, which turned out to be a massive land of resources and magic.

### Beat 21

**reference** 

Climb the tower, get the magic, melt the ice, bring them home. He tells Shim he's becoming a player again.

**candidate** `p0017_05, p0017_06, p0017_07, p0017_10, p0018_01, p0018_02`

Jun-Ho asks what happened next, prompting Deok-gu to explain the Dimensional Elevator has ten floors. He calculates that players should have reached the seventh floor after twenty-five years of progress. Memories of his frozen comrades weigh heavily on his soul as he looks down in silence.

### Beat 22

**reference** 

(no reference beat)

**candidate** `p0018_03, p0018_04, p0018_06, p0018_09, p0018_12, p0018_13, p0018_14, p0018_16`

Jun-Ho asks which floor humanity has reached during his long sleep. Deok-gu remains silent while covering his mouth in shame. After his friend finally mutters a single floor number, he flops onto the mattress in disbelief. He mutters that he has absolutely nothing to say to such a pathetic update.

### Beat 23

**reference** 

(no reference beat)

**candidate** `p0019_01, p0019_02, p0019_03, p0019_04, p0019_05, p0019_09, p0019_10, p0019_11, p0019_12, p0019_13`

Jun-Ho demands to know how they only cleared the second floor, learning that the third floor is a volcanic region requiring the Frost Queen's Nucleus to cool the lava.

### Beat 24

**reference** 

(no reference beat)

**candidate** `p0020_01, p0020_02, p0020_03, p0020_04, p0020_05, p0020_06`

Deok-gu clutches his forehead in deep frustration. He tells Jun-Ho that the association searched the Nest countless times in vain. Hearing this, he breaks into a cold sweat as a sudden realization hits him. He silently thinks that their fruitless search makes perfect sense because he absorbed it himself.

### Beat 25

**reference** 

(no reference beat)

**candidate** `p0020_07, p0020_08, p0020_10, p0020_11, p0020_12, p0020_14`

Jun-Ho hides his mounting panic behind a mask of total calm. Placing a hand on his friend's shoulder, he tells Deok-gu that they were simply unlucky. He smiles while explaining that everyone must be understanding of such a mistake. Deok-gu breaks into joyful tears and shouts that they were definitely not unlucky.

### Beat 26

**reference** 

(no reference beat)

**candidate** `p0020_15, p0021_01, p0021_12, p0021_13, p0022_01, p0022_02, p0022_03, p0022_04, p0022_05, p0022_06, p0022_07`

Jun-Ho wonders when to reveal the truth to avoid a nagging lecture. Deok-gu warns him that the lobby below is crawling with reporters. The facility's archive hall is silent and cold. After clearing authentication, he passes a dragon skeleton to find Skaya and Khali. He sits before his frozen team and apologizes for being late.

### Beat 27

**reference** 

(no reference beat)

**candidate** `p0023_01, p0023_02, p0023_04, p0023_05, p0023_06, p0023_07`

Inside the silent archive, Jun-Ho remembers his team happy and whole before the ice claimed them. He says the world is better because they protected their hard-won peace. Telling them to finally rest, he pours alcohol for Skaya and Khali. Inviting his friends to share a drink, he sits alone on the floor.

### Beat 28

**reference** 

(no reference beat)

**candidate** `p0023_08, p0023_09, p0023_10, p0023_12, p0023_13, p0024_01, p0024_03`

He touches the cold statue of The Swordswoman, another member of the original five heroes currently frozen in ice. He receives a system alert confirming his unique Frost skill can melt the ice. But the message warns him that his magic stats are too low, causing him to fail. He stares in total shock, demanding to know what this means.
