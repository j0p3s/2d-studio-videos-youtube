package com.j0p3s.studio;
import org.junit.Test;
import static org.junit.Assert.*;
public class TimelineTest {
 @Test public void tenMinuteExportHas14400Frames(){assertEquals(14400,Timeline.frames(600000000));assertEquals(599958333,Timeline.frameTime(14399));}
 @Test public void pcmMatchesRealNarrationDuration(){assertEquals(1000000,Timeline.pcmDuration(48000));assertEquals(1440,Timeline.frames(Timeline.pcmDuration(2880000)));}
 @Test(expected=IllegalArgumentException.class) public void rejectsOverTenMinutes(){Timeline.frames(600000001);}
 @Test(expected=IllegalArgumentException.class) public void rejectsEmptyAudio(){Timeline.frames(0);}
}
