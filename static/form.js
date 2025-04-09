// Define VGS form submission using VGScollect library
const vgsForm = window.VGSCollect.create(vaultId = 'tntng36c6tl', environment = 'sandbox', stateCallback = handleVgsFormState)

//The Logic Below is designed to handle form state callbacks
let isVgsFormValid = false
let isCustomerFormValid = true;

const submitButton = document.getElementById('submit-button');
submitButton.setAttribute('disabled', 'true');

function handleVgsFormState(state) {
    if (state.card_cvc.isValid && state.card_number.isValid) {
        isVgsFormValid = true;
    } 
    updateSubmitButtonState();
}
function updateSubmitButtonState() {
    if (isVgsFormValid && isCustomerFormValid) {
        submitButton.removeAttribute('disabled');
    } 
}

// VGS Form Fields Definitions
const css = {
  boxSizing: 'border-box',
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI"',
  color: '#000000',
  '&::placeholder': {
    color: '#bcbcbc'
  }
};

const cardNumber = vgsForm.field('#cc-number', {
  type: 'card-number',
  name: 'card_number',
  placeholder: '4111 1111 1111 1111',
  showCardIcon: true,
  validations: ['required', 'validCardNumber'],
  css: css,
  });

const cardSecurityCode = vgsForm.field('#cc-cvc', {
  type: 'card-security-code',
  name: 'card_cvc',
  placeholder: '123',
  showCardIcon: true,
  validations: ['required', 'validCardSecurityCode'],
  css: css,
  });

const cardHolder = vgsForm.field('#cc-holder', {
  type: 'text',
  name: 'card_holder',
  placeholder: 'John Doe',
  validations: ['required'],
  css: css,
  });

const cardExpDate = vgsForm.field('#cc-expiration-date', {
  type: 'card-expiration-date',
  name: 'card_exp',
  placeholder: 'MM / YY',
  validations: ['required', 'validCardExpirationDate'],
  css: css,
  });
  
// VGS Form Submission
const submitVGSCollectForm = () => {
  
  // Show loading circle
  document.getElementById('loading-circle').style.display = 'block';

  // Get the amount dynamically from the input field
  const amount = document.getElementById('total-amount').value;

  // Submit data
  vgsForm.submit(
    '/post',
    {
      // Additional data from non-VGS fields
      data: {
        amount: amount,
      },
    },
    (status, data) => {
      if (status >= 200 && status <= 300) {

        // Start 3DS flow with Stripe if required
        if (data.payment_intent?.status === 'requires_action') {
          const threeDsUrl = data.payment_intent.next_action.redirect_to_url.url;
          window.location.href = threeDsUrl;
          sessionStorage.setItem('response_data', JSON.stringify(data));
        } else {
          // Render Result Page Otherwise
          window.location.href = '/payment-result';
          sessionStorage.setItem('response_data', JSON.stringify(data));
        }
      } else if (!status) {
        // Network Error occurred
        console.error('Network Error: Please check your internet connection.');
      } else {
        // Server Error
        console.error('Server Error: Status ' + status);
      }
    },
    (validationError) => {
      // Form validation error
      console.error('Form Validation Error:', validationError);
    }
  );
};


// Listen for data submission
document.getElementById('vgs-collect-form').addEventListener('submit', (e) => {
  e.preventDefault();
  submitVGSCollectForm();
}); 
