import { NextRequest, NextResponse } from "next/server";

type SpeechRequest = {
  text?: string;
};

function audioResponse(buffer: ArrayBuffer, contentType: string) {
  return new NextResponse(buffer, {
    headers: {
      "Content-Type": contentType,
      "Cache-Control": "no-store"
    }
  });
}

function base64ToArrayBuffer(value: string) {
  const binary = Buffer.from(value, "base64");
  return binary.buffer.slice(binary.byteOffset, binary.byteOffset + binary.byteLength);
}

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as SpeechRequest;
    const text = body.text?.trim();

    if (!text) {
      return NextResponse.json({ error: "Text is required." }, { status: 400 });
    }

    const apiKey = process.env.SMALLEST_AI_API_KEY;
    const ttsUrl = process.env.SMALLEST_AI_TTS_URL;

    if (!apiKey || !ttsUrl) {
      return NextResponse.json({ error: "smallest.ai voice output is not configured." }, { status: 501 });
    }

    const response = await fetch(ttsUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
        "x-api-key": apiKey
      },
      body: JSON.stringify({
        text,
        voice_id: process.env.SMALLEST_AI_VOICE_ID || "emily",
        output_format: process.env.SMALLEST_AI_OUTPUT_FORMAT || "mp3",
        sample_rate: Number(process.env.SMALLEST_AI_SAMPLE_RATE || 24000)
      })
    });

    if (!response.ok) {
      return NextResponse.json({ error: "smallest.ai voice request failed." }, { status: response.status });
    }

    const contentType = response.headers.get("content-type") || "audio/mpeg";

    if (contentType.includes("application/json")) {
      const payload = await response.json();
      const audioBase64 = payload.audio || payload.audio_base64 || payload.data?.audio || payload.data?.audio_base64;
      const audioUrl = payload.audio_url || payload.url || payload.data?.audio_url;

      if (audioBase64) {
        return audioResponse(base64ToArrayBuffer(audioBase64), "audio/mpeg");
      }

      if (audioUrl) {
        const audio = await fetch(audioUrl);
        if (!audio.ok) throw new Error("Unable to fetch generated Quanty voice audio.");
        return audioResponse(await audio.arrayBuffer(), audio.headers.get("content-type") || "audio/mpeg");
      }

      throw new Error("smallest.ai did not return playable audio.");
    }

    return audioResponse(await response.arrayBuffer(), contentType);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unable to create Quanty voice audio." },
      { status: 500 }
    );
  }
}
