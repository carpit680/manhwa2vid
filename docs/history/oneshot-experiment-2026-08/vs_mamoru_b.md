# Script comparison — reference vs generated

Reference: `reference/frozen_player/mamoru_ch1-2.txt` · Candidate: `experiments/oneshot-fp-ch1-2/arm_b.md`

## Content (does it tell the same story?)

- fact_coverage: **0.47** of 303 salient reference terms
- order_tau: **0.36** (1.0 = same story order, 0 = unrelated, <0 = reversed)
- missing (first 25): answer, 25 years, precise, humanity's, she's, laughing, whole, understands, nothing, bro, cuts, fool, forms, answers, simple, i'll, collide, midair, trading, blows, goku, goku's, speed, gathers, fires

## Style (identical computation on both texts)

| metric | reference | candidate |
|---|---|---|
| beats | 21 | 19 |
| words | 979 | 959 |
| avg_sentence_words | 11.9 | 12.6 |
| caption_markers_per_100w | 0.0 | 0.1 |
| speech_verbs_per_100w | 1.43 | 1.67 |
| connectives_per_100w | 4.19 | 1.88 |
| max_consecutive_pronoun_starts | 3 | 4 ⚠ |
| pronoun_start_fraction | 0.2 | 0.3 |

## Side by side

### Beat 1

**reference** 

To answer that, we have to go back 25 years to be precise. Humanity's final dungeon, and standing at the end of it is the Frost Queen, the monster that froze the Pacific Ocean with a snap. She's laughing in his face, asking how it feels to make it this far. After leaving his whole team behind to die, she tells him he understands nothing about this world.

**candidate** 

# One-shot freeform write — gemini-3.1-pro-preview <!-- project: projects/return-of-the-frozen-player-ch1-2 | temp: 0.9 | tokens: 26650 in / 1205 out --> Deep in the freezing heart of the final dungeon, Seo Jun-Ho stands alone against the crowned monster in an ice gown. The Frost Queen smiles. She asks how it feels to reach her throne room by leaving his comrades behind to die. Jun-Ho draws his blade.

### Beat 2

**reference** 

But Bro cuts her off, saying he's got no time to fool around. She forms a giant blade of pure ice, and he answers with a simple, "I'll kill you and end this nightmare." The two collide midair, trading blows at Goku's speed. She gathers ice magic in her hand and fires it point blank. He dodges by a hair.

**candidate** 

He warns her that his friends are not the type to croak easily. Dark energy surges around his heavy coat. He tells her to shut up. He has no time for this.

### Beat 3

**reference** 

Then in one final exchange, a black flash cuts through the blue silence. The frost queen is on her knees and the guy is standing behind her. She says it was fun. He says he can't say the same.

**candidate** 

He launches himself forward, swearing to end the nightmare. The battle is violently brief. The Queen conjures massive spears of solid ice, but Jun-Ho shatters them with heavy, deliberate strikes. He closes the distance in a blur of dark energy and drives his sword straight through her chest.

### Beat 4

**reference** 

He moves in to finish it, but the moment she starts to glow, his body starts freezing instead. Ice crawling up his arms, his neck, his face, a message telling him he's absorbing the frost queen's core, and he'll stay in hibernation until it's fully absorbed. That's the last thing he sees for 25 years. Now, 76 hours before this fight, five heroes are standing in front of that dungeon, and there's a problem.

**candidate** 

As her body dissolves into light, system messages flood his vision. He is absorbing her nucleus. But victory comes with a steep price. A new message warns that his body will go into forced hibernation until the core is fully assimilated, and ice immediately crawls up his arms, freezing him in place.

### Beat 5

**reference** 

Only one of them can go up those stairs. The big tattooed guy is punching the ice wall, furious that picking one person is the same as telling the rest to die. The cowboy tips his hat and admits they're at a disadvantage, but everyone already knows who has to go. Even the big guy concedes.

**candidate** 

Just seventy-six hours earlier, the Nest Attack Team had hit a dead end. A system prompt declared that only one person could ascend the stairs, causing Khali to slam his fists into the cavern wall, furious they were sidelined. Skaya calmed the tattooed giant down, warning the group their time was short. She suggested Jun-Ho should advance, and the others quickly agreed.

### Beat 6

**reference** 

There's really no one quite like Spectre. The girl agrees, and just like that, four people hand their lives to one man. The whole squad stands facing him, telling him they know their deaths won't be meaningless. He mumbles that not a lot of people would call him their friend.

**candidate** 

The marksman noted their severe disadvantage against ice-based abilities. Khali conceded his spot. The unnamed swordswoman added that Jun-Ho was their absolute best chance, trusting him to make sure their sacrifices mattered. He promised he wouldn't let them down, stepping alone into the cold.

### Beat 7

**reference** 

The cowboy just smiles and says they'd follow him even to death. The healer beams at him saying none of it will be in vain and all he can get out is a quiet you guys before apologizing and walking up those stairs alone. 25 years later, the year is 2024 and we're at a museum exhibit about the monsters humanity still can't defeat. A presenter explains how one man froze the Pacific with a snap of the frost queen's fingers and how five legends walked into Antarctica to stop her.

**candidate** 

Twenty-five years later, that promise sits frozen in a museum. The world of 2024 remembers the Five Heroes as legendary saviors, preserving their frozen bodies as monuments in a climate-controlled hall. A guide is lecturing a crowd when Jun-Ho's ice shell suddenly cracks. The system announces that the absorption rate has reached one hundred percent.

### Beat 8

**reference** 

Those five are displayed right there, frozen in ice. the five heroes. Then a nerdy kid starts screaming, pointing at the exhibit. The ice statue just moved.

**candidate** 

The ice shatters violently, and Jun-Ho collapses onto the floor. He shivers uncontrollably as the system congratulates him for completely absorbing the core, granting him a brand-new skill called Frost EX. The museum erupts into screaming panic. The legendary Specter wakes up.

### Beat 9

**reference** 

The presenter laughs it off, explaining the chamber's temperature is controlled 24/7. There's no way anything happens to those statues. Then she hears the cracking behind her. The ice explodes and a figure burst out of the shards.

**candidate** 

Days later, Jun-Ho sits in a hospital bed, catching up on a quarter-century of news. His body is still terribly weak, his hands shaking just from gripping the table. Looking out at the pristine, monster-free skyline, he figures the world finally got peace. He asks the empty room if this means he is officially unemployed.

### Beat 10

**reference** 

He drops to his knees, shaking as a message tells him the absorption finally hit 100%. The only thing Bro can say after 25 years, co and a new notification, X-rank skill acquired. Frost, the news detonates worldwide within hours. The legend has awakened.

**candidate** 

Deciding he no longer needs it, he removes his signature mask. Nervous doctors usher in the Player Association president. Jun-Ho recognizes him instantly, despite the tailored suit and receding hairline. He asks Deok-gu if they still haven't found a cure for baldness after twenty-five years.

### Beat 11

**reference** 

The spectre is back after 25 years of cryogenic sleep. Meanwhile, the legend himself is sitting in a hospital bed, scrolling headlines like a grandpa who just discovered the internet. It's been 25 years. He tries to make a fist and can barely close his fingers.

**candidate** 

Deok-gu snaps back, asking if insulting his hair is really the first thing his old friend has to say. The touching reunion devolves into immediate bickering. Deok-gu sighs, admitting Jun-Ho hasn't changed a bit. The mood quickly shifts when Jun-Ho asks why the hospital staff is treating him like an active hero.

### Beat 12

**reference** 

The doctors walk in with news. The president of the player association is coming to see him personally. Joan Hull already hates this if it's not someone he knows he's sending them away. But the doctor says the man used to talk with the spectre all the time, a close friend.

**candidate** 

The war should be over. Deok-gu sits down heavily. He tells Jun-Ho that the world only celebrated for about a minute. Safe zones appeared when the Queen died, but a towering dimensional elevator also spawned in the Pacific Ocean.

### Beat 13

**reference** 

And when the guy shows up, bro instantly recognizes him. It's Shimuk. And just like he predicted 25 years ago, dude went completely bald. That's the first thing he says after a 25-year reunion.

**candidate** 

A system prompt announced the opening of the second floor, instructing humanity to stay strong until the tenth floor. Jun-Ho does the mental math. It took their elite team five bloody years to clear the first floor, so realistically, humanity should be around the fifth or seventh floor by now. Deok-gu looks away, avoiding his gaze entirely.

### Beat 14

**reference** 

Shim is furious, saying he was dumb for expecting an emotional moment. Once they're alone, Jono asks the real question. Why is everyone acting weird when the war should be over? So Shim explains, "The day they killed the Frost Queen, the whole world celebrated for about a minute.

**candidate** 

After a long silence, the older man confesses that in twenty-five years, humanity has only cleared the second floor. Jun-Ho is absolutely furious, demanding to know what pathetic excuse justifies stalling for two decades. Deok-gu explains the third floor is a volcanic region entirely covered in magma. Expedition teams found an altar in a sea of lava that required the Frost Queen's nucleus to cool the environment.

### Beat 15

**reference** 

Then a new message dropped. A dimensional elevator appeared in the Pacific, and the second floor was now open. 10 floors total. His team took 5 years to clear the first one.

**candidate** 

He tells Jun-Ho they searched the Nest countless times, but they never found the core. Jun-Ho freezes. He slowly realizes his mistake. He personally absorbed the exact item humanity desperately needed.

### Beat 16

**reference** 

So after 25 years, humanity should be around floor 7, right? Shim can barely say it. In 25 years, humanity cleared one floor. Bro almost falls over.

**candidate** 

Backpedaling his anger immediately, he pats Deok-gu's shoulder and suggests that everyone makes mistakes. Deok-gu enthusiastically agrees. He is completely unaware that Jun-Ho is the sole reason the world is stuck. Wanting to change the subject, Jun-Ho asks about his old comrades.

### Beat 17

**reference** 

25 years, one floor. But there's a reason. The third floor is a sea of lava. And the only way to cool it down is an altar that needs the frost queen's core.

**candidate** 

That night, he sneaks out of the hospital to avoid reporters, heading to the Seoul History Museum with cheap liquor. He walks past massive skeletal displays of conquered monsters to enter the climate-controlled memorial hall. The frozen statues stand silently in the blue light. Jun-Ho sits on the floor.

### Beat 18

**reference** 

They search the nest for decades and never found it. And Jono just goes quiet because he knows exactly where that core is. He at it. It's inside him right now.

**candidate** 

He promises them the world is a better place now, pouring out small paper cups of alcohol. He takes a drink, the sweet taste doing little to dull the bitter reality that they are still trapped in ice. He steps up to Skaya's statue and gently wipes the dust from her frozen hair. His skin touches the ice, and the system flares to life, confirming his possession of the Frost EX skill.

### Beat 19

**reference** 

So he forgives them with the straightest face possible for a mistake they never made. Later, he sneaks out to the history museum, and there they are, his four friends, still frozen, on display like trophies. He sits down, apologizes for being late, and asks them to have a drink with him. But the moment he touches the ice, a message appears.

**candidate** 

A second message warns that his magic stats are insufficient, meaning he has failed to remove the seal. Jun-Ho stares at the floating blue text in pure shock. The system explicitly states the truth. Once he is strong enough, he can use his new skill to unfreeze the statues.

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
