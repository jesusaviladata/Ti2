import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  icon?: ReactNode;
  rightElement?: ReactNode;
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, icon, rightElement, ...props }, ref) => (
    <div className="relative flex items-center">
      {icon && (
        <span className="absolute left-4 text-subtle pointer-events-none">
          {icon}
        </span>
      )}
      <input
        ref={ref}
        className={cn(
          "w-full h-12 bg-inset/60 border border-musgo/25 rounded-lg text-crema placeholder:text-subtle text-sm",
          "focus:outline-none focus:border-arcilla/70 focus:ring-1 focus:ring-arcilla/40",
          "transition-all duration-200",
          icon ? "pl-11 pr-4" : "px-5",
          rightElement && "pr-11",
          className
        )}
        {...props}
      />
      {rightElement && (
        <span className="absolute right-4 text-subtle">{rightElement}</span>
      )}
    </div>
  )
);
Input.displayName = "Input";

export { Input };
