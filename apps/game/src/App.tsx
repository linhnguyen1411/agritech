import React, { useEffect, useRef } from 'react';

import { createGame } from './game';

export default function App() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const game = createGame(containerRef.current);
    return () => {
      game.destroy(true);
    };
  }, []);

  return <div ref={containerRef} id="game-container" />;
}
