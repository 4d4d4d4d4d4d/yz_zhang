import { motion } from 'framer-motion';

const Loading = ({ fullScreen = false, size = 'medium', message = '加载中...' }) => {
  const sizeClasses = {
    small: 'w-8 h-8 border-2',
    medium: 'w-16 h-16 border-4',
    large: 'w-24 h-24 border-4'
  };

  const textSizeClasses = {
    small: 'text-sm',
    medium: 'text-base',
    large: 'text-lg'
  };

  const loadingContent = (
    <div className="flex flex-col items-center justify-center gap-4">
      <div className={`${sizeClasses[size]} border-purple-500 border-t-transparent rounded-full animate-spin`}></div>
      {message && (
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className={`text-gray-400 ${textSizeClasses[size]}`}
        >
          {message}
        </motion.p>
      )}
    </div>
  );

  if (fullScreen) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-gray-900 via-purple-900 to-gray-900 flex items-center justify-center">
        {loadingContent}
      </div>
    );
  }

  return (
    <div className="flex items-center justify-center p-8">
      {loadingContent}
    </div>
  );
};

// Inline loading spinner (for buttons, etc.)
export const InlineLoading = ({ size = 'small', className = '' }) => {
  const sizeClasses = {
    small: 'w-4 h-4 border-2',
    medium: 'w-6 h-6 border-2',
    large: 'w-8 h-8 border-4'
  };

  return (
    <div className={`${sizeClasses[size]} border-white border-t-transparent rounded-full animate-spin ${className}`}></div>
  );
};

// Skeleton loader for content placeholders
export const Skeleton = ({ className = '', variant = 'rect' }) => {
  const variantClasses = {
    rect: 'rounded-lg',
    circle: 'rounded-full',
    text: 'rounded h-4'
  };

  return (
    <div className={`bg-white/10 animate-pulse ${variantClasses[variant]} ${className}`}></div>
  );
};

// Card skeleton for loading cards
export const CardSkeleton = () => {
  return (
    <div className="mystery-card p-6 animate-pulse">
      <div className="flex items-start gap-4">
        <Skeleton variant="circle" className="w-16 h-16 flex-shrink-0" />
        <div className="flex-1 space-y-3">
          <Skeleton className="h-6 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
          <div className="flex gap-2">
            <Skeleton className="h-8 w-20" />
            <Skeleton className="h-8 w-20" />
            <Skeleton className="h-8 w-20" />
          </div>
        </div>
      </div>
    </div>
  );
};

// List skeleton for loading lists
export const ListSkeleton = ({ count = 3 }) => {
  return (
    <div className="space-y-4">
      {Array.from({ length: count }).map((_, index) => (
        <CardSkeleton key={index} />
      ))}
    </div>
  );
};

export default Loading;
