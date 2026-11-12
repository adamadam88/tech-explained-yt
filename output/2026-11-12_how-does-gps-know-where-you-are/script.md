# Your Phone Has No Idea Where It Is. Here's How GPS Finds You Anyway

Topic: How does GPS know where you are? · Voice: af_heart · Length: 6:36

## The trick

**[0:00] hook_title** — Your phone has no idea where it is. Not a clue. And yet, it can find you to within about five meters, almost anywhere on Earth.

**[0:08] globe** — The secret is hidden twenty thousand kilometers above your head. It involves clocks in space, the speed of light, and a correction that only works because Einstein was right.

**[0:19] question** — And the strangest part isn't even the satellites. It's that a tragedy in 1983 is the reason you're allowed to use any of this. We'll get there.

## Clocks in the sky

**[0:29] big_number** — Let's start up there. Right now, about 31 GPS satellites are circling the Earth. Each one flies around 20,200 kilometers up, and loops the planet twice a day.

**[0:41] globe** — They're spread across six orbital planes, tilted at 55 degrees. That layout is deliberate. From virtually anywhere on the planet, at least four of them are always above the horizon.

**[0:53] versus** — And they are fast. Each satellite moves at nearly 14,000 kilometers per hour. That's about fifteen times faster than a passenger jet. Remember that speed. It matters later.

## What satellites say

**[1:06] broadcast** — So what do they actually do? Surprisingly little. Each satellite just keeps broadcasting two things, over and over. Where it is, and exactly what time it is.

**[1:16] flow** — That time comes from atomic clocks on board. And the whole system rests on one simple idea. If you know when a message left, and when it arrived, you know how far it traveled.

**[1:27] big_number** — The signal moves at the speed of light. From directly overhead, the trip takes about 67 thousandths of a second. That's faster than you can blink.

**[1:37] versus** — But here's the problem. Light covers 300 meters in a single microsecond. So if a clock is off by just one millionth of a second, your position is off by about three football fields.

## Drawing circles

**[1:49] circles** — Now let's find you. Here's the flat version. One satellite tells your phone, you are exactly this far from me. That puts you somewhere on a circle.

**[1:59] circles** — A second satellite adds a second circle. They cross at just two points. Add a third, and only one point fits all three. That's you.

**[2:08] tiles** — In real three D space, it's spheres instead of circles, but the idea is exactly the same. It's called trilateration. No angles, no compass. Just distances.

**[2:19] versus** — But wait. That math only works if your phone knows the exact time. And your phone's clock is cheap. It's nowhere near an atomic clock. So how can it time a signal to a millionth of a second?

## Why four satellites

**[2:31] tiles** — The answer is beautiful. Your phone treats time as just another unknown. Latitude, longitude, altitude, and its own clock error. Four unknowns need four measurements. That's why GPS uses four satellites, not three.

**[2:47] top_list** — Solve all four at once, and you get a bonus. Your phone now knows the time to within a millionth of a second. That's why cell networks, power grids and banks lean on GPS as a clock.

## Einstein's correction

**[2:59] clock** — Now, the strange part I promised. Those atomic clocks in orbit don't tick at the same rate as clocks on the ground. Not because they're broken. Because time itself runs differently up there.

**[3:12] versus** — Two effects fight each other. The satellites move so fast that special relativity slows their clocks by about seven microseconds a day. But gravity is weaker up there, so general relativity speeds them up by about 45.

**[3:26] big_number** — The result? Each satellite clock runs about 38 microseconds fast, every single day. That sounds like nothing. But remember, one microsecond is 300 meters.

**[3:38] chart** — Left uncorrected, the error would grow by roughly ten kilometers every day. After a week, your map would put you in a completely different city.

**[3:48] quote** — So engineers set the satellite clocks slightly slow before launch. Instead of ticking at exactly 10.23 megahertz, they're tuned a hair lower. From the ground, they look perfect. Einstein, built into the hardware.

## The 1983 tragedy

**[4:02] timeline** — Now, the history. Because GPS was never meant for you. After Sputnik launched in 1957, physicists realized they could pin down a satellite's orbit just from its radio signal. Flip that around, and a satellite could tell you where you are.

**[4:19] timeline** — The U.S. Navy built a satellite system called Transit to guide its submarines. The first GPS satellite followed in 1978. But GPS was a military system, built for planes, ships and missiles.

**[4:34] quote** — Then, in September 1983, Korean Air Lines Flight 007 strayed off course into Soviet airspace, and was shot down. All 269 people on board were killed.

**[4:48] quote** — About two weeks later, President Reagan announced that GPS would be opened up to civilian aircraft and the world, once it was ready. That's the tragedy that gave you the blue dot.

**[4:59] versus** — But there was a catch. Civilian signals were deliberately degraded. It was called Selective Availability. Then, on May 2nd, 2000, it was switched off. Overnight, typical accuracy jumped from about 45 meters to about 6.

## Why your phone is fast

**[5:15] big_number** — Here's something most people don't know. GPS satellites send their data painfully slowly. Just 50 bits per second. Downloading the full almanac of satellite orbits takes twelve and a half minutes.

**[5:28] flow** — So your phone cheats. It grabs that same data over your mobile network or Wi-Fi, almost instantly. That's called assisted GPS, and it's why your location appears in seconds, not minutes.

**[5:42] noise** — The signal is also incredibly faint. By the time it reaches you, it's weaker than the background radio noise around it. Your phone digs it out using codes it already knows, like picking out a familiar voice in a loud crowd.

**[5:56] top_list** — And your phone doesn't only use GPS. Most modern phones also listen to Europe's Galileo, Russia's GLONASS and China's BeiDou. More satellites in view means a faster, sharper fix, especially between tall buildings.

## Recap

**[6:11] flow** — So here's the whole trick. Satellites shout the time. Your phone measures how late each message arrives. Four of them pin down your position and your clock. And Einstein keeps the whole thing honest.

**[6:24] outro** — Next time that blue dot finds you in a strange city, remember, that's relativity at work. And if you've ever wondered why your phone's battery gets worse every year, that's the video to watch next.

## Sources

- [GPS.gov – Space Segment (constellation, orbits, 31 operational satellites)](https://www.gps.gov/systems/gps/space)
- [GPS.gov – GPS Accuracy (smartphones ~4.9 m under open sky)](https://www.gps.gov/systems/gps/performance/accuracy/)
- [Neil Ashby – Relativity in the Global Positioning System, Living Reviews in Relativity (2003)](https://link.springer.com/article/10.12942/lrr-2003-1)
- [GPS World – Inside the Box: GPS and Relativity (10.22999999543 MHz factory offset)](https://www.gpsworld.com/inside-the-box-gps-and-relativity/)
- [GPS World – The Origins of GPS (Sputnik, Guier & Weiffenbach, Transit)](https://www.gpsworld.com/origins-gps-part-1/)
- [U.S. Air Force – GPS: A Generation of Service (first launch 1978, FOC 1995)](https://www.af.mil/News/Article-Display/Article/601748/gps-a-generation-of-service-to-the-world)
- [Nextgov – How a 1983 Plane Crash Helped Speed Up Civilian Use of GPS](https://nextgov.com/digital-government/2014/11/how-1983-plane-crash-helped-speed-civilian-use-gps/98000)
- [Smithsonian – GPS Accuracy With and Without Selective Availability](https://timeandnavigation.si.edu/multimedia-asset/gps-accuracy-with-and-without-selective-availability)
- [GPS.gov – Selective Availability](https://www.gps.gov/systems/gps/modernization/sa/data)
- [Penn State GEOG 862 – The Almanac, Time to First Fix (50 bps, 12.5 min)](https://courses.ems.psu.edu/geog862/node/1739)
- [Analog Devices – GPS receiver design note (signal below thermal noise)](https://www.analog.com/en/resources/design-notes/designing-a-lowcost-lowcomponentcount-gps-receiver.html)
- [GPS.gov – Timing applications](https://www.gps.gov/applications/timing/)
