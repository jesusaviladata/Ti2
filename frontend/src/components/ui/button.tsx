import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center rounded-pill text-sm font-medium transition-all duration-200 ease-power3-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-arcilla focus-visible:ring-offset-2 focus-visible:ring-offset-carbon disabled:pointer-events-none disabled:opacity-40",
  {
    variants: {
      variant: {
        default:     "bg-arcilla text-crema hover:scale-[1.03] hover:bg-arcilla/90",
        outline:     "border border-musgo bg-transparent text-crema hover:bg-musgo/20",
        ghost:       "text-crema hover:bg-musgo/20",
        destructive: "bg-red-700/80 text-crema hover:bg-red-700",
        secondary:   "bg-musgo text-crema hover:bg-musgo/80",
      },
      size: {
        sm:   "h-9 px-4 text-xs",
        md:   "h-11 px-6",
        lg:   "h-12 px-8 text-base",
        icon: "h-10 w-10 p-0",
      },
    },
    defaultVariants: { variant: "default", size: "md" },
  }
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {}

const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button
      ref={ref}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
);
Button.displayName = "Button";

export { Button, buttonVariants };
