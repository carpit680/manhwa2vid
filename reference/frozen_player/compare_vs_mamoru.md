# Script comparison — reference vs generated

Reference: `reference/frozen_player/mamoru_ch1-2.txt` · Candidate: `projects/return-of-the-frozen-player-ch1-2/script.json`

## Content (does it tell the same story?)

- fact_coverage: **0.46** of 303 salient reference terms
- order_tau: **0.24** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): answer, 25 years, precise, humanity's, dungeon, monster, snap, she's, whole, nothing, cuts, fool, forms, answers, simple, i'll, collide, midair, trading, blows, goku, goku's, speed, fires, blank

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 21 | 28 |
| words | 979 | 1225 |
| avg_sentence_words | 11.9 | 15.5 |
| caption_markers_per_100w | 0.0 | 0.08 |
| speech_verbs_per_100w | 1.43 | 2.04 |
| connectives_per_100w | 4.19 | 2.29 |
| max_consecutive_pronoun_starts | 3 | 2 |
| pronoun_start_fraction | 0.2 | 0.25 |

## Side by side

### Beat 1

**reference** 

To answer that, we have to go back 25 years to be precise. Humanity's final dungeon, and standing at the end of it is the Frost Queen, the monster that froze the Pacific Ocean with a snap. She's laughing in his face, asking how it feels to make it this far. After leaving his whole team behind to die, she tells him he understands nothing about this world.

**candidate** `p0001_02, p0001_03, p0001_04, p0001_05, p0001_06, p0001_07`

Seo Jun-Ho, stands in the vast throne room of the Frost Queen’s Nest to face the final boss. A system alert confirms his encounter as Frost Queen, the final boss of the Antarctic gate, asks if abandoning comrades feels good. He replies that his team won't fall easily and asks if the nightmare ends once she is dead.

### Beat 2

**reference** 

But Bro cuts her off, saying he's got no time to fool around. She forms a giant blade of pure ice, and he answers with a simple, "I'll kill you and end this nightmare." The two collide midair, trading blows at Goku's speed. She gathers ice magic in her hand and fires it point blank. He dodges by a hair.

**candidate** `p0002_01, p0002_02, p0002_03, p0002_04, p0002_05, p0002_06`

The Frost Queen sneers and laughs at his statement, calling him ignorant, but he commands her to shut up and readies his dark blade.

### Beat 3

**reference** 

Then in one final exchange, a black flash cuts through the blue silence. The frost queen is on her knees and the guy is standing behind her. She says it was fun. He says he can't say the same.

**candidate** `p0002_09, p0002_10, p0002_11, p0003_01, p0003_02, p0003_03`

Jun-Ho's boot shatters the frozen floor as he launches into the frigid air. He meets the Frost Queen in a violent collision of dark and light energy. They trade a flurry of lethal strikes across the vast throne room. As sparks fly from their crossing blades, a massive surge of ice energy finally forces him backward.

### Beat 4

**reference** 

He moves in to finish it, but the moment she starts to glow, his body starts freezing instead. Ice crawling up his arms, his neck, his face, a message telling him he's absorbing the frost queen's core, and he'll stay in hibernation until it's fully absorbed. That's the last thing he sees for 25 years. Now, 76 hours before this fight, five heroes are standing in front of that dungeon, and there's a problem.

**candidate** `p0003_04, p0003_05, p0003_06, p0004_01, p0004_02, p0004_03, p0004_04, p0004_05`

The Frost Queen smiles and gathers a blinding sphere of energy in her palm. Jun-Ho gasps in shock as a massive explosion of light and ice shatters the throne room. He lands in a low crouch while shards of the frozen floor rain down around him. Finally, he stands victoriously over his defeated foe in the quiet hall.

### Beat 5

**reference** 

Only one of them can go up those stairs. The big tattooed guy is punching the ice wall, furious that picking one person is the same as telling the rest to die. The cowboy tips his hat and admits they're at a disadvantage, but everyone already knows who has to go. Even the big guy concedes.

**candidate** `p0005_01, p0005_02, p0005_04, p0005_06, p0005_08, p0005_10, p0005_11`

Frost Queen smiles while fading into light, admitting the battle was fun. Jun-Ho looks on coldly and replies that he cannot say the same. One final strike triggers a blinding explosion, but he gasps as ice suddenly races across his skin. A system alert mandates hibernation, a restorative sleep, to absorb her nucleus.

### Beat 6

**reference** 

There's really no one quite like Spectre. The girl agrees, and just like that, four people hand their lives to one man. The whole squad stands facing him, telling him they know their deaths won't be meaningless. He mumbles that not a lot of people would call him their friend.

**candidate** `p0005_12, p0005_14, p0006_02, p0006_03, p0006_04, p0006_05, p0006_06, p0006_07, p0006_08, p0006_09`

Twenty-five years ago in Antarctica, Khali, the tattooed giant of the original five-member hero party, and Skaya, the white-haired healer of the original five-member hero party, debated who should go up the stairs.

### Beat 7

**reference** 

The cowboy just smiles and says they'd follow him even to death. The healer beams at him saying none of it will be in vain and all he can get out is a quiet you guys before apologizing and walking up those stairs alone. 25 years later, the year is 2024 and we're at a museum exhibit about the monsters humanity still can't defeat. A presenter explains how one man froze the Pacific with a snap of the frost queen's fingers and how five legends walked into Antarctica to stop her.

**candidate** `p0007_02, p0007_03, p0007_04, p0007_05, p0007_06, p0007_07`

Khali reluctantly yields to the decision, and Skaya, who believes in their leader's strength, reaffirms that only Specter has the elemental advantage to face the boss.

### Beat 8

**reference** 

Those five are displayed right there, frozen in ice. the five heroes. Then a nerdy kid starts screaming, pointing at the exhibit. The ice statue just moved.

**candidate** `p0007_08, p0007_09, p0007_10, p0007_11, p0008_02, p0008_03`

Jun-Ho stands at a distance and faces his four trusted comrades. The marksman smiles alongside Skaya. He replies that they might if their leader loses the final battle and they all die in vain. But they still trust him completely, and Seo Jun-Ho simply looks forward in silence.

### Beat 9

**reference** 

The presenter laughs it off, explaining the chamber's temperature is controlled 24/7. There's no way anything happens to those statues. Then she hears the cracking behind her. The ice explodes and a figure burst out of the shards.

**candidate** `p0008_04, p0008_05, p0008_06, p0008_07, p0008_08, p0008_09`

Skaya smiles warmly and tells Jun-Ho she knows he will not let their deaths be in vain. While the team stands together in absolute faith, she asks for his confirmation. He acknowledges their trust as they insist only he can finish the fight, apologizing for the heavy burden they leave behind.

### Beat 10

**reference** 

He drops to his knees, shaking as a message tells him the absorption finally hit 100%. The only thing Bro can say after 25 years, co and a new notification, X-rank skill acquired. Frost, the news detonates worldwide within hours. The legend has awakened.

**candidate** `p0008_10, p0008_11, p0008_12, p0008_13, p0009_01, p0009_02, p0009_03, p0009_04, p0009_05, p0009_06`

Twenty-five years later, a museum presenter exhibits the frozen statues of the five heroes to an audience, detailing the terrifying power of the Frost Queen.

### Beat 11

**reference** 

The spectre is back after 25 years of cryogenic sleep. Meanwhile, the legend himself is sitting in a hospital bed, scrolling headlines like a grandpa who just discovered the internet. It's been 25 years. He tries to make a fist and can barely close his fingers.

**candidate** `p0009_07, p0009_08, p0009_09, p0009_10, p0010_03, p0010_04`

Thick ice holds the hand of him completely frozen inside the memorial. The schoolboy points toward the stage and says that the frozen statue just moved. Dismissing the claim, the presenter tells the boy that he is incorrect. But small shards of ice suddenly flake off from him. The presenter looks back in confusion just before the ice shatters violently. Terrified by the blast, the presenter says that this is impossible.

### Beat 12

**reference** 

The doctors walk in with news. The president of the player association is coming to see him personally. Joan Hull already hates this if it's not someone he knows he's sending them away. But the doctor says the man used to talk with the spectre all the time, a close friend.

**candidate** `p0010_05, p0010_06, p0010_08, p0011_01, p0011_02, p0011_03, p0011_04, p0011_05`

He bursts from his icy monument in a violent explosion of flying shards. He crashes to the museum floor, shivering violently as he draws his first freezing breath. Shuddering on the cold ground, he says that it is freezing. Floating system windows announce that he has absorbed the boss's nucleus to unlock a new frost skill.

### Beat 13

**reference** 

And when the guy shows up, bro instantly recognizes him. It's Shimuk. And just like he predicted 25 years ago, dude went completely bald. That's the first thing he says after a 25-year reunion.

**candidate** `p0011_06, p0012_01, p0012_02, p0012_03, p0012_04, p0012_07, p0012_09, p0012_10, p0012_12, p0012_14`

The presenter’s voice fades as he reads news in his hospital room. He mutters in shock that twenty-five years have passed. His hands tremble as he admits he can barely clench a fist. When the chief doctor, the hospital’s lead physician, reports that the Player Association president is arriving, he chuckles, knowing he has few friends.

### Beat 14

**reference** 

Shim is furious, saying he was dumb for expecting an emotional moment. Once they're alone, Jono asks the real question. Why is everyone acting weird when the war should be over? So Shim explains, "The day they killed the Frost Queen, the whole world celebrated for about a minute.

**candidate** `p0013_01, p0013_02, p0013_03, p0013_04, p0013_05, p0013_07`

He looks out the window at the modern skyscrapers of the peaceful world, reflecting on the quiet future his frozen teammates had sacrificed everything to protect.

### Beat 15

**reference** 

Then a new message dropped. A dimensional elevator appeared in the Pacific, and the second floor was now open. 10 floors total. His team took 5 years to clear the first one.

**candidate** `p0013_08, p0013_12, p0013_15, p0013_16, p0013_17, p0013_18`

Jun-Ho looks down thoughtfully while gripping his old black face mask. The chief doctor, the hospital’s leading physician, enters and stammers the name Specter in total disbelief. He asks why he would finally reveal his face. The nurse, an attending ward medic, and the young doctor, an assistant physician, stand frozen.

### Beat 16

**reference** 

So after 25 years, humanity should be around floor 7, right? Shim can barely say it. In 25 years, humanity cleared one floor. Bro almost falls over.

**candidate** `p0014_01, p0014_03, p0014_04, p0014_05, p0014_07, p0014_08`

Deok-gu, the Player Association president and old friend of Jun-Ho, marches inside with his bodyguards. He asks the flustered medical staff what is wrong as they scramble aside. He stares in shock at the balding man who promises to explain everything. The president requests a private conversation, and the doctors bow before leaving them alone.

### Beat 17

**reference** 

25 years, one floor. But there's a reason. The third floor is a sea of lava. And the only way to cool it down is an altar that needs the frost queen's core.

**candidate** `p0014_09, p0014_10, p0014_11, p0015_01, p0015_02, p0015_03`

Deok-gu reveals severe hair loss. He stands by the hospital bed and says that Jun-Ho looks exactly the same. Recognizing that familiar voice, he gasps in surprise and smiles broadly. But the sentimental moment quickly turns to teasing as he points and laughs. He points and laughs at Deok-gu for having severe M-pattern baldness.

### Beat 18

**reference** 

They search the nest for decades and never found it. And Jono just goes quiet because he knows exactly where that core is. He at it. It's inside him right now.

**candidate** `p0015_04, p0015_06, p0015_07, p0015_08, p0016_05, p0016_06`

As the two men settle down, they transition to a serious discussion about the aftermath of the final battle, recalling the day safe zones appeared on Earth.

### Beat 19

**reference** 

So he forgives them with the straightest face possible for a mistake they never made. Later, he sneaks out to the history museum, and there they are, his four friends, still frozen, on display like trophies. He sits down, apologizes for being late, and asks them to have a drink with him. But the moment he touches the ice, a message appears.

**candidate** `p0016_07, p0016_08, p0016_09, p0016_10, p0016_11, p0016_13, p0016_16`

A massive crowd fills the city streets, cheering and crying tears of joy over the victory. But he knows that the world never lets such pure happiness last for very long. A sudden chime echoes everywhere as the system announces a dimensional elevator is installed in the Pacific Ocean. The stunned audience members gasp in silent shock, demanding to know what is happening above them.

### Beat 20

**reference** 

The skill frost axe can free them from the frozen prison, but his magic stat is too low. Seal removal failed. His stats went back to level one after the hibernation, but every floor of the elevator cleared gives a permanent boost. So, the plan writes itself.

**candidate** `p0016_18, p0016_19, p0016_20, p0017_02, p0017_03, p0017_04`

The system announces that travel to the Frontier, a gateway to higher floors, is now possible. Outraged audience members scream that this is nonsense and the Queen should have been the end. He reflects that leaders eventually organized an expedition squad. This floor provided humanity with magic, technology, and vast knowledge.

### Beat 21

**reference** 

Climb the tower, get the magic, melt the ice, bring them home. He tells Shim he's becoming a player again.

**candidate** `p0017_05, p0017_06, p0017_07, p0017_10, p0018_01, p0018_02`

However, Deok-gu nervously reveals that they are still stuck on the second floor, causing his legendary friend to collapse back onto his bed in utter disbelief.

### Beat 22

**reference** 

(no reference beat)

**candidate** `p0018_03, p0018_04, p0018_06, p0018_09, p0018_12, p0018_13, p0018_14, p0018_16`

Demanding a proper explanation, Jun-Ho learns that the third floor is a volcanic region that cannot be explored without the cooling power of the Frost Queen's Nucleus.

### Beat 23

**reference** 

(no reference beat)

**candidate** `p0019_01, p0019_02, p0019_03, p0019_04, p0019_05, p0019_09, p0019_10, p0019_11, p0019_12, p0019_13`

Deok-gu admits they searched the nest countless times in vain, unaware that Jun-Ho had already absorbed the nucleus into his own body during his long slumber.

### Beat 24

**reference** 

(no reference beat)

**candidate** `p0020_01, p0020_02, p0020_03, p0020_04, p0020_05, p0020_06`

Jun-Ho keeps the secret to himself and gently comforts Deok-gu, telling him the players were simply unlucky, which moves the weeping president to tears of joy.

### Beat 25

**reference** 

(no reference beat)

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
