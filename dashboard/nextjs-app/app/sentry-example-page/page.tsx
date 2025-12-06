"use client";

import * as Sentry from "@sentry/nextjs";
import { useState } from "react";

export default function SentryExamplePage() {
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const throwFrontendError = () => {
    try {
      throw new Error("This is a test error from the frontend!");
    } catch (error) {
      Sentry.captureException(error);
      setErrorMessage("Frontend error captured! Check Sentry dashboard.");
    }
  };

  const throwUnhandledError = () => {
    // This will trigger an unhandled error
    throw new Error("Unhandled frontend error!");
  };

  const testLogging = () => {
    const { logger } = Sentry;
    logger.info("Test info log from Sentry example page");
    logger.warn("Test warning log from Sentry example page");
    logger.error("Test error log from Sentry example page");
    setErrorMessage("Logs sent to Sentry! Check Sentry dashboard.");
  };

  const testTracing = () => {
    Sentry.startSpan(
      {
        op: "ui.click",
        name: "Test Button Click",
      },
      (span) => {
        span.setAttribute("button", "test-tracing");
        span.setAttribute("page", "sentry-example-page");
        // Simulate some work
        setTimeout(() => {
          setErrorMessage("Trace sent to Sentry! Check Sentry dashboard.");
        }, 100);
      },
    );
  };

  return (
    <div className="container mx-auto p-8">
      <h1 className="text-3xl font-bold mb-6">Sentry Integration Test Page</h1>
      <p className="mb-8 text-gray-600">
        Use the buttons below to test different Sentry features. Check your
        Sentry dashboard to verify that errors, logs, and traces are being
        captured.
      </p>

      <div className="space-y-4">
        <div className="p-4 border rounded">
          <h2 className="text-xl font-semibold mb-2">Error Monitoring</h2>
          <div className="space-x-2">
            <button
              onClick={throwFrontendError}
              className="px-4 py-2 bg-red-500 text-white rounded hover:bg-red-600"
            >
              Throw Handled Error
            </button>
            <button
              onClick={throwUnhandledError}
              className="px-4 py-2 bg-red-700 text-white rounded hover:bg-red-800"
            >
              Throw Unhandled Error
            </button>
          </div>
        </div>

        <div className="p-4 border rounded">
          <h2 className="text-xl font-semibold mb-2">Logging</h2>
          <button
            onClick={testLogging}
            className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
          >
            Send Test Logs
          </button>
        </div>

        <div className="p-4 border rounded">
          <h2 className="text-xl font-semibold mb-2">Tracing</h2>
          <button
            onClick={testTracing}
            className="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600"
          >
            Create Test Trace
          </button>
        </div>
      </div>

      {errorMessage && (
        <div className="mt-4 p-4 bg-yellow-100 border border-yellow-400 rounded">
          <p className="text-yellow-800">{errorMessage}</p>
        </div>
      )}
    </div>
  );
}
