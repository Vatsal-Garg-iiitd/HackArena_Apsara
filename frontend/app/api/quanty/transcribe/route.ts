import { NextRequest, NextResponse } from "next/server";

const llmUrl = process.env.QUANTY_LLM_API_URL || "";

function extractGeminiText(payload: unknown) {
  const candidates = (payload as { candidates?: Array<{ content?: { parts?: Array<{ text?: string }> } }> })
    .candidates;

  return candidates?.[0]?.content?.parts
    ?.map((part) => part.text)
    .filter(Boolean)
    .join("\n")
    .trim();
}

export async function POST(request: NextRequest) {
  try {
    const apiKey = process.env.QUANTY_LLM_API_KEY;
    if (!apiKey) {
      return NextResponse.json({ error: "Quanty transcription is not configured." }, { status: 501 });
    }

    if (!llmUrl.includes("generativelanguage.googleapis.com")) {
      return NextResponse.json({ error: "Audio transcription currently requires Gemini configuration." }, { status: 501 });
    }

    const formData = await request.formData();
    const audio = formData.get("audio");

    if (!(audio instanceof File) || audio.size === 0) {
      return NextResponse.json({ error: "A recorded audio file is required." }, { status: 400 });
    }

    const bytes = Buffer.from(await audio.arrayBuffer());
    const response = await fetch(llmUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-goog-api-key": apiKey
      },
      body: JSON.stringify({
        contents: [
          {
            role: "user",
            parts: [
              {
                text: "Transcribe this audio into plain written text. Return only the transcript, with no commentary."
              },
              {
                inlineData: {
                  mimeType: audio.type || "audio/webm",
                  data: bytes.toString("base64")
                }
              }
            ]
          }
        ],
        generationConfig: {
          temperature: 0,
          maxOutputTokens: 260
        }
      })
    });

    if (!response.ok) {
      const details = await response.text();
      console.error("Quanty transcription request failed", response.status, details);
      return NextResponse.json({ error: "Quanty could not transcribe that recording." }, { status: 502 });
    }

    const transcript = extractGeminiText(await response.json());
    if (!transcript) {
      return NextResponse.json({ error: "No speech was detected in that recording." }, { status: 422 });
    }

    return NextResponse.json({ transcript });
  } catch (error) {
    console.error("Quanty transcription failed", error);
    return NextResponse.json({ error: "Unable to transcribe the recording." }, { status: 500 });
  }
}
