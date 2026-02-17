"use client";

import { useEffect, useRef } from "react";

interface VoiceOrbProps {
  isListening: boolean;
  isSpeaking: boolean;
  isProcessing: boolean;
  audioLevel?: number; // 0-1
  onActivate: () => void;
  onDeactivate: () => void;
}

export default function VoiceOrb({
  isListening,
  isSpeaking,
  isProcessing,
  audioLevel = 0,
  onActivate,
  onDeactivate,
}: VoiceOrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const animationRef = useRef<number>();
  const timeRef = useRef(0);

  const isActive = isListening || isSpeaking || isProcessing;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const size = 200;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    ctx.scale(dpr, dpr);

    const centerX = size / 2;
    const centerY = size / 2;
    const baseRadius = 60;

    const animate = () => {
      timeRef.current += 0.016;
      const t = timeRef.current;

      ctx.clearRect(0, 0, size, size);

      // Background glow
      if (isActive) {
        const glowGradient = ctx.createRadialGradient(
          centerX,
          centerY,
          0,
          centerX,
          centerY,
          100
        );
        glowGradient.addColorStop(0, "rgba(120, 120, 255, 0.15)");
        glowGradient.addColorStop(0.5, "rgba(200, 100, 255, 0.08)");
        glowGradient.addColorStop(1, "rgba(255, 100, 200, 0)");
        ctx.fillStyle = glowGradient;
        ctx.fillRect(0, 0, size, size);
      }

      // Wave layers (Siri-style)
      const numLayers = 4;
      for (let layer = 0; layer < numLayers; layer++) {
        ctx.beginPath();

        const layerOffset = layer * 0.5;
        const amplitude = isActive
          ? 8 + audioLevel * 25 + Math.sin(t * 2 + layer) * 5
          : 2 + Math.sin(t + layer) * 1;

        for (let angle = 0; angle <= Math.PI * 2; angle += 0.05) {
          const wave1 = Math.sin(angle * 3 + t * 3 + layerOffset) * amplitude;
          const wave2 = Math.sin(angle * 5 - t * 2 + layerOffset) * amplitude * 0.5;
          const wave3 = Math.sin(angle * 7 + t * 4 + layerOffset) * amplitude * 0.3;

          const radiusOffset = wave1 + wave2 + wave3;
          const radius = baseRadius + radiusOffset;

          const x = centerX + Math.cos(angle) * radius;
          const y = centerY + Math.sin(angle) * radius;

          if (angle === 0) {
            ctx.moveTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
        }

        ctx.closePath();

        // Gradient colors based on state
        let colors: string[];
        if (isSpeaking) {
          colors = [
            `hsla(${280 + layer * 20}, 80%, 60%, ${0.4 - layer * 0.08})`,
            `hsla(${320 + layer * 15}, 90%, 65%, ${0.4 - layer * 0.08})`,
            `hsla(${200 + layer * 10}, 85%, 55%, ${0.4 - layer * 0.08})`,
          ];
        } else if (isListening) {
          colors = [
            `hsla(${120 + Math.sin(t) * 30}, 70%, 55%, ${0.4 - layer * 0.08})`,
            `hsla(${180 + Math.sin(t * 0.8) * 30}, 80%, 60%, ${0.4 - layer * 0.08})`,
            `hsla(${240 + Math.sin(t * 1.2) * 30}, 75%, 58%, ${0.4 - layer * 0.08})`,
          ];
        } else if (isProcessing) {
          colors = [
            `hsla(${40 + t * 50 % 360}, 90%, 55%, ${0.4 - layer * 0.08})`,
            `hsla(${80 + t * 50 % 360}, 85%, 60%, ${0.4 - layer * 0.08})`,
            `hsla(${120 + t * 50 % 360}, 80%, 55%, ${0.4 - layer * 0.08})`,
          ];
        } else {
          colors = [
            `hsla(220, 15%, 50%, ${0.2 - layer * 0.04})`,
            `hsla(240, 15%, 55%, ${0.2 - layer * 0.04})`,
            `hsla(260, 15%, 50%, ${0.2 - layer * 0.04})`,
          ];
        }

        const gradient = ctx.createLinearGradient(
          centerX - baseRadius,
          centerY - baseRadius,
          centerX + baseRadius,
          centerY + baseRadius
        );
        gradient.addColorStop(0, colors[0]);
        gradient.addColorStop(0.5, colors[1]);
        gradient.addColorStop(1, colors[2]);

        ctx.fillStyle = gradient;
        ctx.fill();
      }

      // Inner core orb
      ctx.beginPath();
      const coreRadius = isActive ? 30 + audioLevel * 8 : 28;
      ctx.arc(centerX, centerY, coreRadius, 0, Math.PI * 2);

      const coreGradient = ctx.createRadialGradient(
        centerX - 10,
        centerY - 10,
        0,
        centerX,
        centerY,
        coreRadius
      );

      if (isActive) {
        coreGradient.addColorStop(0, "rgba(255, 255, 255, 0.95)");
        coreGradient.addColorStop(0.3, "rgba(200, 180, 255, 0.9)");
        coreGradient.addColorStop(0.7, "rgba(150, 100, 255, 0.8)");
        coreGradient.addColorStop(1, "rgba(100, 50, 200, 0.7)");
      } else {
        coreGradient.addColorStop(0, "rgba(255, 255, 255, 0.8)");
        coreGradient.addColorStop(0.5, "rgba(200, 200, 220, 0.6)");
        coreGradient.addColorStop(1, "rgba(150, 150, 180, 0.4)");
      }

      ctx.fillStyle = coreGradient;
      ctx.fill();

      // Highlight
      ctx.beginPath();
      ctx.arc(centerX - 8, centerY - 8, 8, 0, Math.PI * 2);
      const highlightGradient = ctx.createRadialGradient(
        centerX - 8,
        centerY - 8,
        0,
        centerX - 8,
        centerY - 8,
        8
      );
      highlightGradient.addColorStop(0, "rgba(255, 255, 255, 0.8)");
      highlightGradient.addColorStop(1, "rgba(255, 255, 255, 0)");
      ctx.fillStyle = highlightGradient;
      ctx.fill();

      animationRef.current = requestAnimationFrame(animate);
    };

    animate();

    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [isListening, isSpeaking, isProcessing, audioLevel, isActive]);

  const handleClick = () => {
    if (isActive) {
      onDeactivate();
    } else {
      onActivate();
    }
  };

  return (
    <div className="flex flex-col items-center gap-4">
      <button
        onClick={handleClick}
        className={`relative transition-transform duration-300 ${
          isActive ? "scale-110" : "hover:scale-105"
        }`}
        aria-label={isActive ? "Stop voice mode" : "Start voice mode"}
      >
        <canvas
          ref={canvasRef}
          className="cursor-pointer"
          style={{ touchAction: "none" }}
        />
        
        {/* Pulse ring animation */}
        {isActive && (
          <>
            <div className="absolute inset-0 rounded-full border-2 border-purple-400/30 animate-ping" />
            <div
              className="absolute inset-0 rounded-full border border-purple-300/20 animate-pulse"
              style={{ animationDelay: "0.5s" }}
            />
          </>
        )}
      </button>

      {/* Status text */}
      <div className="text-center">
        <p
          className={`text-sm font-medium transition-colors ${
            isActive ? "text-purple-600" : "text-gray-500"
          }`}
        >
          {isSpeaking
            ? "Speaking..."
            : isProcessing
            ? "Processing..."
            : isListening
            ? "Listening..."
            : "Tap to speak"}
        </p>
        {isListening && (
          <p className="text-xs text-gray-400 mt-1">Tap again to stop</p>
        )}
      </div>
    </div>
  );
}
