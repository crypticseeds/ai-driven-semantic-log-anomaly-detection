import * as Sentry from "@sentry/nextjs";
import { NextResponse } from "next/server";

export async function GET() {
  try {
    // Test logging
    const { logger } = Sentry;
    logger.info("API route called: /api/sentry-example");

    // Test tracing
    return Sentry.startSpan(
      {
        op: "http.server",
        name: "GET /api/sentry-example",
      },
      async () => {
        // Simulate some work
        await new Promise((resolve) => setTimeout(resolve, 100));

        return NextResponse.json({
          message: "Sentry API route test successful",
          timestamp: new Date().toISOString(),
        });
      },
    );
  } catch (error) {
    Sentry.captureException(error);
    return NextResponse.json(
      { error: "An error occurred" },
      { status: 500 },
    );
  }
}

export async function POST() {
  // This endpoint intentionally throws an error to test error monitoring
  throw new Error("This is a test error from the API route!");
}
