# Script comparison — reference vs generated

Reference: `reference/frozen_player/mamoru_ch1-2.txt` · Candidate: `experiments/oneshot-fp-ch1-2/arm_f_clean_prompt.md`

## Content (does it tell the same story?)

- fact_coverage: **0.42** of 303 salient reference terms
- order_tau: **0.26** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): answer, 25 years, precise, dungeon, pacific ocean, ocean, snap, she's, asking, leaving, whole, understands, bro, cuts, saying, fool, forms, pure, answers, simple, i'll, nightmare, collide, midair, trading

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 21 | 15 |
| words | 979 | 1020 |
| avg_sentence_words | 11.9 | 17.3 |
| caption_markers_per_100w | 0.0 | 0.0 |
| speech_verbs_per_100w | 1.43 | 0.39 ⚠ |
| connectives_per_100w | 4.19 | 1.96 |
| max_consecutive_pronoun_starts | 3 | 1 |
| pronoun_start_fraction | 0.2 | 0.24 |

## Side by side

### Beat 1

**reference** 

To answer that, we have to go back 25 years to be precise. Humanity's final dungeon, and standing at the end of it is the Frost Queen, the monster that froze the Pacific Ocean with a snap. She's laughing in his face, asking how it feels to make it this far. After leaving his whole team behind to die, she tells him he understands nothing about this world.

**candidate** 

The frozen throne room cracks under the pressure of humanity's absolute last hope. Seo Jun-Ho, the masked swordsman in the black coat, stares down the Frost Queen. She is a crowned monster in an ice gown, and she laughs at his desperate stance. Earth has been steadily freezing over, turning into a dead rock, and Jun-Ho is the only one left standing with a chance to stop it.

### Beat 2

**reference** 

But Bro cuts her off, saying he's got no time to fool around. She forms a giant blade of pure ice, and he answers with a simple, "I'll kill you and end this nightmare." The two collide midair, trading blows at Goku's speed. She gathers ice magic in her hand and fires it point blank. He dodges by a hair.

**candidate** 

He grips his blade, ignoring the biting cold tearing at his lungs. The queen warns him that his pathetic human efforts are completely useless, but Jun-Ho rushes forward anyway, ready to violently end this long winter. Ice spikes erupt from the absolute zero floor, threatening to impale him. Jun-Ho dodges them with lethal agility, closing the distance while the queen casually waves her pale hand.

### Beat 3

**reference** 

Then in one final exchange, a black flash cuts through the blue silence. The frost queen is on her knees and the guy is standing behind her. She says it was fun. He says he can't say the same.

**candidate** 

She fires a massive beam of concentrated freezing energy right at his chest. Jun-Ho deflects it with his sword, the sheer concussive force shattering the ancient ice pillars all around them. He leaps high into the frigid air, bringing his weapon down in a devastating, glowing arc. The blade strikes true, piercing straight through the Frost Queen's neck.

### Beat 4

**reference** 

He moves in to finish it, but the moment she starts to glow, his body starts freezing instead. Ice crawling up his arms, his neck, his face, a message telling him he's absorbing the frost queen's core, and he'll stay in hibernation until it's fully absorbed. That's the last thing he sees for 25 years. Now, 76 hours before this fight, five heroes are standing in front of that dungeon, and there's a problem.

**candidate** 

The impact shatters her core like cheap glass, scattering light across the cavern. A system message immediately announces that the Frost Queen's Nest has been cleared, officially marking the end of the deadly Antarctica zone. But monumental victory comes with a truly brutal price tag. Jun-Ho turns around to survey the quiet cavern, his breath pluming in the dark.

### Beat 5

**reference** 

Only one of them can go up those stairs. The big tattooed guy is punching the ice wall, furious that picking one person is the same as telling the rest to die. The cowboy tips his hat and admits they're at a disadvantage, but everyone already knows who has to go. Even the big guy concedes.

**candidate** 

He sees the rest of the Nest Attack Team standing together in a group. The tattooed giant Khali, the white-haired healer Skaya, along with Rahat and Mio, are all permanently trapped in solid blocks of magical ice. They deliberately sacrificed themselves to hold the line, creating the tiny opening he needed to land that final, desperate blow. Jun-Ho walks over to the shattered remains of the boss and slowly picks up the Frost Queen's nucleus.

### Beat 6

**reference** 

There's really no one quite like Spectre. The girl agrees, and just like that, four people hand their lives to one man. The whole squad stands facing him, telling him they know their deaths won't be meaningless. He mumbles that not a lot of people would call him their friend.

**candidate** 

It pulses with a dangerous, chilling light. He knows exactly how the system rules work, which is a grim burden. Consuming the boss core is the only way to gain the Frost (EX) skill, an absolute necessity to prevent the ice from spreading globally. But it immediately forces the user's body into a deep, indefinite hibernation.

### Beat 7

**reference** 

The cowboy just smiles and says they'd follow him even to death. The healer beams at him saying none of it will be in vain and all he can get out is a quiet you guys before apologizing and walking up those stairs alone. 25 years later, the year is 2024 and we're at a museum exhibit about the monsters humanity still can't defeat. A presenter explains how one man froze the Pacific with a snap of the frost queen's fingers and how five legends walked into Antarctica to stop her.

**candidate** 

Jun-Ho swallows the glowing core without a single second thought. The narration delivers '[YOUR MAGIC POWER HAS INCREASED BY 1.]' and "[YOU HAVE OBTAINED THE NEW SKILL, 'FROST (EX)'.]" Frost instantly begins to creep up his arms, encasing his entire body in thick, unbreakable ice. The system confirms his suspended animation, locking his stats in place. As the cold darkness finally takes him, Jun-Ho closes his eyes, hoping his legendary team will be remembered by the world they just saved.

### Beat 8

**reference** 

Those five are displayed right there, frozen in ice. the five heroes. Then a nerdy kid starts screaming, pointing at the exhibit. The ice statue just moved.

**candidate** 

Twenty-five years later, the magical ice finally thaws. Jun-Ho wakes up in a sunlit, sterile hospital bed, utterly disoriented and gasping for warm air. The system cheerfully greets the frozen player, announcing that his long hibernation is finally over and his new skill is stable. He pulls off his heavy mask, staring out the wide window at a modern, bustling metropolis that looks absolutely nothing like the apocalyptic wasteland he left behind.

### Beat 9

**reference** 

The presenter laughs it off, explaining the chamber's temperature is controlled 24/7. There's no way anything happens to those statues. Then she hears the cracking behind her. The ice explodes and a figure burst out of the shards.

**candidate** 

He finds a tablet resting nearby and starts frantically swiping through the unfamiliar interface. A quick web search catches him up on a wild quarter-century of missed history. The world obviously didn't end, but it definitely changed. Instead of plunging into an ice age, a massive dimensional elevator appeared, turning reality into a literal tower of floors for awakened players to conquer.

### Beat 10

**reference** 

He drops to his knees, shaking as a message tells him the absorption finally hit 100%. The only thing Bro can say after 25 years, co and a new notification, X-rank skill acquired. Frost, the news detonates worldwide within hours. The legend has awakened.

**candidate** 

Jun-Ho reads the news articles, realizing that he has become a literal myth. The masked swordsman in the black coat is universally celebrated in textbooks as the supreme savior of mankind. But right now, he just feels like a guy who slept through the entire cultural revolution. He checks his own stats, noting that the system shows an error message 'Player information cannot be found', before the hospital room door violently bursts open.

### Beat 11

**reference** 

The spectre is back after 25 years of cryogenic sleep. Meanwhile, the legend himself is sitting in a hospital bed, scrolling headlines like a grandpa who just discovered the internet. It's been 25 years. He tries to make a fist and can barely close his fingers.

**candidate** 

A squad of serious men in dark suits stands aside to make way for a very stressed man. It is the bald association president, rushing into the room completely out of breath. This is Shim Deok-Gu, Jun-Ho's old friend from the original days, looking considerably older and missing entirely too much hair. Deok-Gu stares hard at the young man sitting on the bed, tears immediately welling up in his tired eyes as he calls out Jun-Ho's name.

### Beat 12

**reference** 

The doctors walk in with news. The president of the player association is coming to see him personally. Joan Hull already hates this if it's not someone he knows he's sending them away. But the doctor says the man used to talk with the spectre all the time, a close friend.

**candidate** 

They fiercely hug it out, the heavy decades of worry and grief melting away in an instant. Once the tears stop, Deok-Gu sits down to explain the grim state of the new world. He tells Jun-Ho that while he was peacefully asleep, humanity aggressively pushed forward into the tower, establishing a new society. But they are currently completely stuck on the second floor of the dimensional elevator.

### Beat 13

**reference** 

And when the guy shows up, bro instantly recognizes him. It's Shimuk. And just like he predicted 25 years ago, dude went completely bald. That's the first thing he says after a 25-year reunion.

**candidate** 

The frontier is ridiculously brutal, and top-tier players are dying in droves trying to break the ceiling. Deok-Gu admits that they desperately need their greatest hero back in the game, because nobody else has the raw power to clear the blockage. Jun-Ho listens quietly, absorbing the heavy reality that his war is far from over. Deok-Gu takes Jun-Ho down to a highly secure, climate-controlled vault deep beneath the association headquarters.

### Beat 14

**reference** 

Shim is furious, saying he was dumb for expecting an emotional moment. Once they're alone, Jono asks the real question. Why is everyone acting weird when the war should be over? So Shim explains, "The day they killed the Frost Queen, the whole world celebrated for about a minute.

**candidate** 

Inside, the frozen bodies of the Five Heroes stand like tragic, beautiful statues in the dim light, perfectly preserved just as they were in Antarctica. Deok-Gu completely breaks down, crying as he confesses his deep guilt over sending his absolute best friends to their icy doom all those years ago. Jun-Ho watches his old friend weep, feeling the immense weight of their lost time and shared trauma. He slowly walks up to the statues, placing a warm hand on the thick ice trapping the white-haired healer.

### Beat 15

**reference** 

Then a new message dropped. A dimensional elevator appeared in the Pacific, and the second floor was now open. 10 floors total. His team took 5 years to clear the first one.

**candidate** 

He fully expects the ice to feel just as cold and unforgiving as it did during the final battle. But right then, a glowing blue system message violently flashes before his eyes, changing everything. The text clearly states that he is now perfectly able to remove the seal on the ice status.

### Beat 16

**reference** 

So after 25 years, humanity should be around floor 7, right? Shim can barely say it. In 25 years, humanity cleared one floor. Bro almost falls over.

**candidate** 

(no candidate beat)

### Beat 17

**reference** 

25 years, one floor. But there's a reason. The third floor is a sea of lava. And the only way to cool it down is an altar that needs the frost queen's core.

**candidate** 

(no candidate beat)

### Beat 18

**reference** 

They search the nest for decades and never found it. And Jono just goes quiet because he knows exactly where that core is. He at it. It's inside him right now.

**candidate** 

(no candidate beat)

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
