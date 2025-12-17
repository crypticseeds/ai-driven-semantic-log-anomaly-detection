"use client";

import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface LoadingProps {
    className?: string;
    size?: "sm" | "md" | "lg";
    text?: string;
}

const sizeClasses = {
    sm: "h-4 w-4",
    md: "h-6 w-6",
    lg: "h-8 w-8",
};

export function Loading({ className, size = "md", text }: LoadingProps) {
    return (
        <div className={cn("flex flex-col items-center justify-center gap-2", className)}>
            <Loader2 className={cn("animate-spin text-primary", sizeClasses[size])} />
            {text && <p className="text-sm text-muted-foreground">{text}</p>}
        </div>
    );
}

export function LoadingSpinner({ className, size = "md" }: Omit<LoadingProps, "text">) {
    return <Loader2 className={cn("animate-spin text-primary", sizeClasses[size], className)} />;
}

