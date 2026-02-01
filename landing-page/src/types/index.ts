export interface LandingPageContent {
    title: string;
    description: string;
    features: string[];
    callToAction: string;
}

export interface User {
    name: string;
    email: string;
    message: string;
}

export type FormSubmissionResponse = {
    success: boolean;
    message: string;
};