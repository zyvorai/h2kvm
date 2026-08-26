// Copyright (c) 2026 ZyvorAI Labs Private Limited. All rights reserved.

import { motion, type HTMLMotionProps } from 'framer-motion';

const spring = { type: 'spring' as const, stiffness: 300, damping: 25, mass: 0.8 };

export type GlassCardProps = HTMLMotionProps<'div'> & {
  elevated?: boolean;
  strong?: boolean;
  hover?: boolean;
};

export function GlassCard({
  elevated = true,
  strong = false,
  hover = true,
  className = '',
  children,
  ...props
}: GlassCardProps) {
  const glassClass = strong ? 'glass-strong' : elevated ? 'glass-elevated glass' : 'glass';
  return (
    <motion.div
      whileHover={hover ? { scale: 1.005 } : undefined}
      transition={spring}
      className={`${glassClass} ${hover ? 'glass-hover-lift' : ''} ${className}`.trim()}
      {...props}
    >
      {children}
    </motion.div>
  );
}
