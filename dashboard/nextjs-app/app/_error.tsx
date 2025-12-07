"use client";

import * as Sentry from "@sentry/nextjs";
import { useEffect } from "react";
import { NextPageContext } from "next";

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function Error({ error, reset }: ErrorProps) {
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);

  return (
    <div className="container mx-auto p-8">
      <h1 className="text-3xl font-bold mb-4">Something went wrong!</h1>
      <p className="mb-4 text-gray-600">
        An error has been reported to Sentry. Our team has been notified.
      </p>
      <button
        onClick={reset}
        className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
      >
        Try again
      </button>
    </div>
  );
}


