import React from 'react';
import {Composition} from 'remotion';

import {Sqrt2Pole} from './Sqrt2Pole';

export const Root: React.FC = () => {
  return (
    <>
      <Composition
        id="Sqrt2Pole"
        component={Sqrt2Pole}
        durationInFrames={30}
        fps={30}
        width={1080}
        height={1920}
      />
    </>
  );
};
