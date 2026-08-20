# Script comparison — reference vs generated

Reference: `reference/frozen_player/mamoru_ch1-2.txt` · Candidate: `projects/return-of-the-frozen-player-ch1-2/script.json`

## Content (does it tell the same story?)

- fact_coverage: **0.44** of 303 salient reference terms
- order_tau: **0.29** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): answer, 25 years, precise, she's, feels, make, leaving, whole, understands, nothing, bro, cuts, fool, around, giant, blade, pure, answers, simple, i'll, nightmare, collide, midair, trading, goku

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 21 | 18 |
| words | 979 | 984 |
| avg_sentence_words | 11.9 | 16.1 |
| caption_markers_per_100w | 0.0 | 0.0 |
| speech_verbs_per_100w | 1.43 | 1.63 |
| connectives_per_100w | 4.19 | 2.24 |
| max_consecutive_pronoun_starts | 3 | 2 |
| pronoun_start_fraction | 0.2 | 0.25 |

## Side by side

### Beat 1

**reference** 

To answer that, we have to go back 25 years to be precise. Humanity's final dungeon, and standing at the end of it is the Frost Queen, the monster that froze the Pacific Ocean with a snap. She's laughing in his face, asking how it feels to make it this far. After leaving his whole team behind to die, she tells him he understands nothing about this world.

**candidate** `p0001_02, p0001_03, p0001_04, p0001_05, p0001_06, p0001_07, p0002_01, p0002_02, p0002_03, p0002_04, p0002_05, p0002_06`

Twenty-five years ago, Seo Jun-Ho confronts the Frost Queen, the ruler of the final dungeon in Antarctica, in her Nest's throne room, where he draws his weapon and vows to slay her.

### Beat 2

**reference** 

But Bro cuts her off, saying he's got no time to fool around. She forms a giant blade of pure ice, and he answers with a simple, "I'll kill you and end this nightmare." The two collide midair, trading blows at Goku's speed. She gathers ice magic in her hand and fires it point blank. He dodges by a hair.

**candidate** `p0002_09, p0002_10, p0002_11, p0003_01, p0003_02, p0003_03, p0003_04, p0003_05, p0003_06, p0004_01, p0004_02, p0004_03, p0004_04, p0004_05`

An intense battle erupts as Jun-Ho clashes with the Frost Queen, exchanging rapid blows and shattering the frozen ground.

### Beat 3

**reference** 

Then in one final exchange, a black flash cuts through the blue silence. The frost queen is on her knees and the guy is standing behind her. She says it was fun. He says he can't say the same.

**candidate** `p0005_01, p0005_02, p0005_04, p0005_06, p0005_08, p0005_10`

Frost Queen smiles as she begins to dissipate into light, admitting that the battle was fun. Jun-Ho looks down coldly and replies that he cannot say the same. Even as a brilliant flash of energy erupts, he delivers one final strike to end the fight. Thick layers of ice suddenly crawl up his body while the monster vanishes completely. He wonders what is happening as the frost rapidly encases his face and limbs.

### Beat 4

**reference** 

He moves in to finish it, but the moment she starts to glow, his body starts freezing instead. Ice crawling up his arms, his neck, his face, a message telling him he's absorbing the frost queen's core, and he'll stay in hibernation until it's fully absorbed. That's the last thing he sees for 25 years. Now, 76 hours before this fight, five heroes are standing in front of that dungeon, and there's a problem.

**candidate** `p0005_11, p0005_12, p0005_14, p0006_02, p0006_03, p0006_04, p0006_05, p0006_06, p0006_07, p0006_08, p0006_09`

A system prompt explains that he must enter hibernation to absorb the nucleus. A flashback to twenty-five years ago reveals Khali, the team's tattooed vanguard who yielded his spot to Jun-Ho, venting his frustration because only one person can advance. Skaya, the party's white-haired healer who stayed behind during the Nest raid, nominates Seo Jun-Ho to go, and the marksman, the team's cowboy-hat-wearing marksman, agrees.

### Beat 5

**reference** 

Only one of them can go up those stairs. The big tattooed guy is punching the ice wall, furious that picking one person is the same as telling the rest to die. The cowboy tips his hat and admits they're at a disadvantage, but everyone already knows who has to go. Even the big guy concedes.

**candidate** `p0007_02, p0007_03, p0007_04, p0007_05, p0007_06, p0007_07, p0007_08, p0007_09, p0007_10, p0007_11, p0008_02, p0008_03`

Khali concedes to the choice, prompting the swordswoman, the team's short-haired swordswoman, to express her full agreement. Although Jun-Ho asks if they will regret their decision, his comrades reassure him of their absolute trust.

### Beat 6

**reference** 

There's really no one quite like Spectre. The girl agrees, and just like that, four people hand their lives to one man. The whole squad stands facing him, telling him they know their deaths won't be meaningless. He mumbles that not a lot of people would call him their friend.

**candidate** `p0008_04, p0008_05, p0008_06, p0008_07, p0008_08, p0008_09, p0008_10, p0008_11, p0008_12, p0008_13, p0009_01, p0009_02`

Skaya smiles, encouraging him not to let their sacrifices be in vain. Twenty-five years later, a presenter in a modern auditorium lectures an audience about the Frost Queen's terrifying abilities, while a schoolboy asks about Jun-Ho and his Nest Attack Team.

### Beat 7

**reference** 

The cowboy just smiles and says they'd follow him even to death. The healer beams at him saying none of it will be in vain and all he can get out is a quiet you guys before apologizing and walking up those stairs alone. 25 years later, the year is 2024 and we're at a museum exhibit about the monsters humanity still can't defeat. A presenter explains how one man froze the Pacific with a snap of the frost queen's fingers and how five legends walked into Antarctica to stop her.

**candidate** `p0009_03, p0009_04, p0009_05, p0009_06, p0009_07, p0009_08, p0009_09, p0009_10`

Bright stage lights hum as the story shifts to a modern museum auditorium. The presenter snaps his fingers to unveil five massive blocks of ancient ice. He tells the audience that these legendary figures are known as the Five Heroes. Spectators gaze at the frozen forms of Khali and Skaya held in permanent slumber. Deep inside the monument, the hand of Jun-Ho remains perfectly preserved within the frost. A schoolboy points toward the stage and shouts that the ice statue just... The presenter dismisses the child as incorrect before leading the crowd away. Tiny shards of ice begin to splinter from the body

### Beat 8

**reference** 

Those five are displayed right there, frozen in ice. the five heroes. Then a nerdy kid starts screaming, pointing at the exhibit. The ice statue just moved.

**candidate** `p0010_03, p0010_04, p0010_05, p0010_06, p0010_08, p0011_01`

The presenter turns back toward the statues in confusion as the central monument begins to crack. While they shout that there is no way this is happening, the ice violently shatters into jagged shards. He bursts from his prison and collapses onto the museum floor, his body trembling uncontrollably. Shivering in the open air, he mutters that he is freezing.

### Beat 9

**reference** 

The presenter laughs it off, explaining the chamber's temperature is controlled 24/7. There's no way anything happens to those statues. Then she hears the cracking behind her. The ice explodes and a figure burst out of the shards.

**candidate** `p0011_02, p0011_03, p0011_04, p0011_05, p0011_06, p0012_01, p0012_02, p0012_03, p0012_04, p0012_07, p0012_09`

While the crowd panics, system notifications confirm that Jun-Ho has absorbed the Frost Queen's nucleus, gaining the Frost (EX) skill. Later in a hospital room, he reads news of his twenty-five-year slumber and laments his weakened hands just as the medical staff announces the Player Association President is arriving.

### Beat 10

**reference** 

He drops to his knees, shaking as a message tells him the absorption finally hit 100%. The only thing Bro can say after 25 years, co and a new notification, X-rank skill acquired. Frost, the news detonates worldwide within hours. The legend has awakened.

**candidate** `p0012_10, p0012_12, p0012_14, p0013_01, p0013_02, p0013_03, p0013_04, p0013_05, p0013_07, p0013_08, p0013_12, p0013_15`

Jun-Ho stares down at his own open hand as the chief doctor watches him. He admits that very few people would ever call him their true friend. Still, he thanks the doctor for delivering the honest news. Memories of his fallen comrades suddenly flash before his eyes. He envisions Skaya standing tall. Beside her stands Khali. The group also includes the marksman and the swordswoman. Looking toward the bright sky, he whispers that his old friends achieved their dream. They successfully created the peaceful, safe world they always wanted. He walks over to the massive window to survey the bustling modern city below. Countless soaring skyscrapers stretch out across the vast horizon. He realizes his grueling battles finally secured this lasting peace. Preparing for the next hunt, he raises his black face mask. He gazes down thoughtfully as he braces himself for an unfamiliar future.

### Beat 11

**reference** 

The spectre is back after 25 years of cryogenic sleep. Meanwhile, the legend himself is sitting in a hospital bed, scrolling headlines like a grandpa who just discovered the internet. It's been 25 years. He tries to make a fist and can barely close his fingers.

**candidate** `p0013_16, p0013_17, p0013_18, p0014_01, p0014_03, p0014_04, p0014_05, p0014_07, p0014_08, p0014_09, p0014_10, p0014_11`

He looks down at the black mask that once defined his legendary identity. The chief doctor freezes and whispers that he is Specter, the era's greatest hunter. He asks why the hero would reveal his face now while the staff trembles in shock. He just smiles warmly at their confusion until the hospital room door swings open. Shim Deok-gu, the Player Association president and his old friend, enters the room with his bodyguards.

### Beat 12

**reference** 

The doctors walk in with news. The president of the player association is coming to see him personally. Joan Hull already hates this if it's not someone he knows he's sending them away. But the doctor says the man used to talk with the spectre all the time, a close friend.

**candidate** `p0015_01, p0015_02, p0015_03, p0015_04, p0015_06, p0015_07, p0015_08, p0016_05, p0016_06, p0016_07`

Jun-Ho bursts out laughing at Shim Deok-gu's baldness, but their reunion quickly turns serious as they sit down to talk. The president recounts how humanity rejoiced and safe zones appeared worldwide immediately after the Frost Queen was defeated.

### Beat 13

**reference** 

And when the guy shows up, bro instantly recognizes him. It's Shimuk. And just like he predicted 25 years ago, dude went completely bald. That's the first thing he says after a 25-year reunion.

**candidate** `p0016_08, p0016_09, p0016_10, p0016_11, p0016_13, p0016_16, p0016_18, p0016_19, p0016_20, p0017_02, p0017_03, p0017_04`

The global celebration was short-lived, as a massive Dimensional Elevator suddenly appeared in the Pacific Ocean. World leaders quickly organized an expedition to the second floor, which yielded advanced magic, technology, and resources for the players, including his silhouetted team.

### Beat 14

**reference** 

Shim is furious, saying he was dumb for expecting an emotional moment. Once they're alone, Jono asks the real question. Why is everyone acting weird when the war should be over? So Shim explains, "The day they killed the Frost Queen, the whole world celebrated for about a minute.

**candidate** `p0017_05, p0017_06, p0017_07, p0017_10, p0018_01, p0018_02, p0018_03, p0018_04, p0018_06, p0018_09, p0018_12, p0018_13, p0018_14, p0018_16`

He asks about their current progress, expecting them to be far higher than the second floor after twenty-five years. He collapses back onto his hospital bed in utter disbelief when Shim Deok-gu admits that humanity's progress has completely stalled.

### Beat 15

**reference** 

Then a new message dropped. A dimensional elevator appeared in the Pacific, and the second floor was now open. 10 floors total. His team took 5 years to clear the first one.

**candidate** `p0019_01, p0019_02, p0019_03, p0019_04, p0019_05, p0019_09, p0019_10, p0019_11, p0019_12, p0019_13`

Jun-Ho sits up in a fury, demanding to know how they only cleared the second floor. Shim Deok-gu explains that the third floor is a volcanic region where further exploration is blocked by a sea of lava that can only be cooled down by the missing Frost Queen's nucleus.

### Beat 16

**reference** 

So after 25 years, humanity should be around floor 7, right? Shim can barely say it. In 25 years, humanity cleared one floor. Bro almost falls over.

**candidate** `p0020_01, p0020_02, p0020_03, p0020_04, p0020_05, p0020_06, p0020_07, p0020_08, p0020_10, p0020_11, p0020_12, p0020_14`

After Shim Deok-gu laments that searching the Nest for the nucleus was useless, Seo Jun-Ho silently realizes he absorbed it himself. He pats his old friend on the shoulder to comfort him, moving the president to tears of gratitude.

### Beat 17

**reference** 

25 years, one floor. But there's a reason. The third floor is a sea of lava. And the only way to cool it down is an altar that needs the frost queen's core.

**candidate** `p0020_15, p0021_01, p0021_12, p0021_13, p0022_01, p0022_02, p0022_03, p0022_04, p0022_05, p0022_06, p0022_07`

To avoid the reporters waiting outside the hospital, Seo Jun-Ho secretly heads to the museum's secure basement vault. After passing authentication, he enters a cold hall and sits before the frozen statues of his four teammates, apologizing for being late.

### Beat 18

**reference** 

They search the nest for decades and never found it. And Jono just goes quiet because he knows exactly where that core is. He at it. It's inside him right now.

**candidate** `p0023_01, p0023_02, p0023_04, p0023_05, p0023_06, p0023_07, p0023_08, p0023_09, p0023_10, p0023_12, p0023_13, p0024_01, p0024_03`

Remembering their happy times, Jun-Ho pours alcohol into paper cups to share a drink with his frozen teammates. However, when he touches the swordswoman to wipe away the dust, a system notification alerts him that his magic stats are too low to break the seal.

### Beat 19

**reference** 

So he forgives them with the straightest face possible for a mistake they never made. Later, he sneaks out to the history museum, and there they are, his four friends, still frozen, on display like trophies. He sits down, apologizes for being late, and asks them to have a drink with him. But the moment he touches the ice, a message appears.

**candidate** 

(no candidate beat)

### Beat 20

**reference** 

The skill frost axe can free them from the frozen prison, but his magic stat is too low. Seal removal failed. His stats went back to level one after the hibernation, but every floor of the elevator cleared gives a permanent boost. So, the plan writes itself.

**candidate** 

(no candidate beat)

### Beat 21

**reference** 

Climb the tower, get the magic, melt the ice, bring them home. He tells Shim he's becoming a player again.

**candidate** 

(no candidate beat)
