// Render Server Side Response as a JSON
const response_data = JSON.parse(sessionStorage.getItem('response_data'));
const jsonString = JSON.stringify(response_data, null, 2);
document.getElementById('detailed-response').innerHTML = `<pre>${jsonString}</pre>`;
console.log(response_data);

//
const stripe = Stripe('pk_test_51PmT2DRvsWphrOcNkBcP7BAI4hesoecRvCaLblFG2IwsKXAS7GYgwLqLTKHHGPyl4WpFFfdI1k7BgUHQU5v8NwCj0032ZjqBkt');
const url_query_params = new URLSearchParams(window.location.search);
pi_secret = url_query_params.get('payment_intent_client_secret')
stripe.retrievePaymentIntent(pi_secret)
.then(function(result) {
  if (result.error) {
    // PaymentIntent client secret was invalid
  } else {
    if (result.paymentIntent.status === 'succeeded') {
      document.getElementById('result-output').textContent = '3DS verification and payment execution is successful';
    } else if (result.paymentIntent.status === 'requires_payment_method') {
        document.getElementById('result-output').textContent = '3DS verification and payment execution failed';
    }
  }
});

