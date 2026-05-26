import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';

export const Sqrt2Pole: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();

  const growFrames = Math.round(fps * 0.5);
  const barScaleX = interpolate(frame, [0, growFrames], [1, 3], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp'
  });

  return (
    <AbsoluteFill
      style={{
        backgroundColor: '#fff',
        justifyContent: 'center',
        alignItems: 'center'
      }}
    >
      <svg
        width={720}
        height={360}
        viewBox="0 0 720 360"
        style={{display: 'block'}}
      >
        <path
          d="M 120 190 L 175 285 L 250 95 L 300 95"
          fill="none"
          stroke="#000"
          strokeWidth={22}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <g transform={`translate(300 95) scale(${barScaleX} 1)`}>
          <line
            x1={0}
            y1={0}
            x2={180}
            y2={0}
            stroke="#000"
            strokeWidth={22}
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        </g>
        <text
          x={320}
          y={275}
          fill="#000"
          fontSize={220}
          fontFamily="Times New Roman, Times, serif"
        >
          2
        </text>
      </svg>
    </AbsoluteFill>
  );
};
