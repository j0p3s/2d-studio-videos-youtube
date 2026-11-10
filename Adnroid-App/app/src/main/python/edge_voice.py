"""Uses upstream edge-tts directly, rather than duplicating its changing wire protocol."""
import asyncio
import os
import edge_tts

VOICE = "en-US-AndrewMultilingualNeural"

def synthesize(text, filename):
    async def generate():
        from java import jclass
        thread = jclass("java.lang.Thread").currentThread()
        received = 0
        partial = filename + ".partial"
        try:
            with open(partial, "wb") as output:
                async for chunk in edge_tts.Communicate(text, VOICE, rate="-5%").stream():
                    if thread.isInterrupted():
                        raise RuntimeError("Speech cancelled")
                    if chunk["type"] == "audio":
                        output.write(chunk["data"])
                        received += len(chunk["data"])
            if received < 100:
                raise RuntimeError("Edge returned no audio")
            os.replace(partial, filename)
        finally:
            if os.path.exists(partial):
                os.remove(partial)
    asyncio.run(asyncio.wait_for(generate(), timeout=90))
    return filename
