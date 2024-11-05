How to make DOOM render (very slowly) on vt520 terminal 

vt520 is (almost) a top terminal out there
https://web.mit.edu/dosathena/doc/www/ek-vt520-rm.pdf

1. Get pre rendered DOOM frame.
2. Upscale it to 640x400.
3. Dither to bw
4. Split it to 64x25 blocks = 1600 blocks, each 10x16 pixels.
So far, so good. Now, here lies The Problem!
1600 > 256
Fortunately vt520 can be pushed to WYSE160 mode
From manual "WYSE 160: You can display all 512 characters in the four font banks on
the screen at the same time."
It is still less than 1600 but 512 10x16 individual pixel blocks are a LOT. Lot more than zx or NES
5. No i have to find an algorithm to detect "similar" blocks so I can reduce size to 512 blocks per frame. // TODO
But lets stay at 512 club. 512 x 10 x 16 = 81920
It takes mere 0.7 seconds to load WYSE 160 font. THEORETICALLY. There are header and usage commands also. But still... a breathtaking 1 FPS pereparation time is theoretically achievable.
To send actual frame (ASCII string) we need to send 2000 bytes. 2000 bytes is 16 000 bits.
togeher with font 97920 bits per second to achieve whopping 1 FPS. And we still have ~ 2KB/s to waste for overhead.

Yet antoher point of optimization. Blocks that are absolute inverse (1s instead of 0s and vice versa) can loaded only once as font and sent with "inverse" attribute set. 
This may be huge advantage because it theoretically gives us 512 blocks and additional 512 "inversed" blocks. 

Also 520 characters have "dim" attribute. This gives us weird "3-"color"" black-white-gray "palette". 
so 512+512+512 altogether. Theoretically. This should be bleny of playroom. 

I think this problem need deeper analysis. Finding "similar" fields and merging them to one - galois fields may help there.
But.. this is purely mathematical approach. Two fields that differ by just few pixels may be "close" mathematically but they belong to bigger picture. 
So 6 bits can be just "noise" OR they can be significant detail (like goom-guy eye). Bits that create status bar are similar to bits that create landscape in a math. sense, 
but much more significant in gameplay sense. This is going to be tough!

We need to extract more information from DOOM engine and separate it to classes

1. Wireframes that make up floor ceilings etc. class A
2. status bar - class A
3. Monsters. class B
4. sprites - class D
5. textures - class F

So class A gets A treatment. Fully rendered. Class B - some replacements allowed. Classes D and F - whatever left over. 

Of course, higher classes blocks can, and will be, re-used on lower priority classes. 
